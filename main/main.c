#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "freertos/queue.h"
#include "driver/gptimer.h"
#include "esp_rom_sys.h"
#include "esp_log.h"
#include "esp_system.h"
#include "huffman.h"

#define SIZE 1024
#define SEED 42
#define PERIOD_US 30000
#define MAX_SAMPLES 10000
static uint32_t samples[MAX_SAMPLES];
static uint8_t input[SIZE], shared[SIZE];
static SemaphoreHandle_t mutex;
static QueueHandle_t releases;
static TaskHandle_t high_task, low_task, stress_task;
static int64_t next_release;
static volatile unsigned dropped;
static int64_t now_us(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (int64_t)t.tv_sec * 1000000 + t.tv_nsec / 1000;
}
static bool release_cb(gptimer_handle_t t, const gptimer_alarm_event_data_t *e, void *ctx) {
    BaseType_t wake = pdFALSE;
    int64_t stamp = next_release;
    next_release += PERIOD_US;
    if (xQueueSendFromISR(releases, &stamp, &wake) != pdTRUE) dropped++;
    return wake == pdTRUE;
}
static bool stress_cb(gptimer_handle_t t, const gptimer_alarm_event_data_t *e, void *ctx) {
    esp_rom_delay_us(120);
    return false;
}
static gptimer_handle_t make_timer(uint64_t period, bool periodic, bool stress) {
    gptimer_handle_t t;
    gptimer_config_t cfg = {.clk_src=GPTIMER_CLK_SRC_DEFAULT,.direction=GPTIMER_COUNT_UP,.resolution_hz=1000000};
    ESP_ERROR_CHECK(gptimer_new_timer(&cfg, &t));
    gptimer_event_callbacks_t cb = {.on_alarm=stress ? stress_cb : release_cb};
    ESP_ERROR_CHECK(gptimer_register_event_callbacks(t, &cb, NULL));
    gptimer_alarm_config_t alarm = {.alarm_count=period,.reload_count=0,.flags.auto_reload_on_alarm=periodic};
    ESP_ERROR_CHECK(gptimer_set_alarm_action(t, &alarm));
    ESP_ERROR_CHECK(gptimer_enable(t));
    return t;
}
static void destroy_timer(gptimer_handle_t t) {
    ESP_ERROR_CHECK(gptimer_stop(t));
    ESP_ERROR_CHECK(gptimer_disable(t));
    ESP_ERROR_CHECK(gptimer_del_timer(t));
}
static void competitor(void *arg) {
    bool high = (intptr_t)arg == 1;
    TickType_t last = xTaskGetTickCount();
    for (;;) {
        xTaskDelayUntil(&last, pdMS_TO_TICKS(high ? 4 : 25));
        xSemaphoreTake(mutex, portMAX_DELAY);
        shared[high ? 0 : 1]++;
        esp_rom_delay_us(high ? 500 : 1200);
        xSemaphoreGive(mutex);
    }
}
static void stress(void *arg) {
    volatile uint8_t *arena = calloc(32768, 1);
    configASSERT(arena);
    for (;;) {
        for (unsigned j=0; j<40; j++)
            for (unsigned i=0; i<32768; i+=32) arena[i]++;
        vTaskDelay(1);
    }
}
static void campaign(void *arg) {
    printf("META,idf=%s,cpu_mhz=%d,cores=%d,tick_hz=%d,array=%d,seed=%d\n",
        esp_get_idf_version(), CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ, portNUM_PROCESSORS, configTICK_RATE_HZ, SIZE, SEED);
    for (int stage=1; stage<=4; stage++) {
        const int count = stage == 4 ? 10000 : 1000;
        gptimer_handle_t event = NULL, irq = NULL;
        srand(SEED);
        dropped = 0;
        printf("MEDINDO_ETAPA_%d,N=%d\n", stage, count);
        fflush(stdout);
        vTaskDelay(pdMS_TO_TICKS(100));
        if (stage >= 3) {
            configASSERT(xTaskCreatePinnedToCore(competitor,"alta",2048,(void *)1,5,&high_task,1)==pdPASS);
            configASSERT(xTaskCreatePinnedToCore(competitor,"baixa",2048,NULL,2,&low_task,1)==pdPASS);
        }
        if (stage == 4) {
            configASSERT(xTaskCreatePinnedToCore(stress,"carga",2048,NULL,4,&stress_task,0)==pdPASS);
            irq = make_timer(500,true,true);
            ESP_ERROR_CHECK(gptimer_start(irq));
        }
        if (stage >= 2) event = make_timer(PERIOD_US,stage>=3,false);
        for (int i=0; i<count; i++) {
            for (int j=0; j<SIZE; j++) input[j]=(uint8_t)(rand()%256);
            int64_t start;
            if (stage == 1) start = now_us();
            else {
                if (i == 0 || stage == 2) {
                    ESP_ERROR_CHECK(gptimer_set_raw_count(event,0));
                    next_release = now_us() + PERIOD_US;
                    ESP_ERROR_CHECK(gptimer_start(event));
                }
                configASSERT(xQueueReceive(releases,&start,portMAX_DELAY)==pdTRUE);
                if (stage == 2) ESP_ERROR_CHECK(gptimer_stop(event));
            }
            if (stage >= 3) {
                xSemaphoreTake(mutex,portMAX_DELAY);
                memcpy(shared,input,SIZE);
                xSemaphoreGive(mutex);
            }
            int ok = executar_tarefa_huffman(input,SIZE);
            int64_t end = now_us();
            if (!ok || dropped || end < start || end-start > UINT32_MAX) {
                printf("ERRO,etapa=%d,ativacao=%d,ok=%d,dropped=%u\n",stage,i+1,ok,dropped);
                abort();
            }
            samples[i]=(uint32_t)(end-start);
            if (stage == 1) vTaskDelay(1);
        }
        if (event) {
            if (stage == 2) ESP_ERROR_CHECK(gptimer_start(event));
            destroy_timer(event);
        }
        if (irq) destroy_timer(irq);
        if (stage >= 3) {
            /* Wait for mutex owners to finish before deleting suspended workers. */
            xSemaphoreTake(mutex,portMAX_DELAY);
            vTaskDelete(high_task);
            vTaskDelete(low_task);
            xSemaphoreGive(mutex);
        }
        if (stage == 4) { /* stress arena lives until reboot; no allocations after this stage */
            vTaskDelete(stress_task);
        }
        xQueueReset(releases);
        printf("=== INICIO_CSV_ETAPA_%d ===\nativacao,tempo_us\n",stage);
        for (int i=0;i<count;i++) {
            printf("%d,%" PRIu32 "\n",i+1,samples[i]);
            /* Serial output is outside all measured intervals; let idle/WDT run. */
            if ((i+1)%100 == 0) vTaskDelay(1);
        }
        printf("=== FIM_CSV_ETAPA_%d ===\n",stage);
    }
    printf("CAMPANHA_CONCLUIDA\n");
    vTaskDelete(NULL);
}
void app_main(void) {
    esp_log_level_set("*", ESP_LOG_NONE);
    mutex=xSemaphoreCreateMutex();
    releases=xQueueCreate(32,sizeof(int64_t));
    configASSERT(mutex && releases);
    configASSERT(configTICK_RATE_HZ == 1000);
    configASSERT(xTaskCreatePinnedToCore(campaign,"huffman",8192,NULL,3,NULL,1)==pdPASS);
}
