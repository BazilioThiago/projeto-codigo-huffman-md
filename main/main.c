/*
 * SPDX-FileCopyrightText: 2010-2022 Espressif Systems (Shanghai) CO LTD
 *
 * SPDX-License-Identifier: CC0-1.0
 */

#include <inttypes.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <stdio.h>
#include <time.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "driver/gptimer.h"
#include "freertos/task.h"
#include "esp_chip_info.h"
#include "esp_rom_sys.h"
#include "esp_system.h"
#include "esp_flash.h"
#include "sdkconfig.h"
#include "esp_log.h"
#include "huffman.h"


/* =========================================================================
 * CONFIGURACAO DO EXPERIMENTO (ALTERE APENAS ESTAS MACROS ENTRE OS TESTES)
 * ========================================================================= */
#define ETAPA_ATUAL        1      /* 1=Tarefa, 2=Comportamental, 3=Intertarefas, 4=Sistema */
#define TOTAL_ATIVACOES    1000   /* Use 10000 em uma das etapas para o Experimento B */
#define TAMANHO_ARRAY      4096   /* Fixo em todas as etapas (4 KB -> ~2.500 a 3.500 us) */
#define SEED_FIXA          42     /* Fixa em todas as etapas */

/* Recursos compartilhados */
static uint8_t buffer_compartilhado[TAMANHO_ARRAY];
static SemaphoreHandle_t sem_evento = NULL;
static SemaphoreHandle_t mutex_recurso = NULL;
static volatile bool teste_em_andamento = true;

static inline double calcular_tempo_us(struct timespec inicio, struct timespec fim) {
    return (fim.tv_sec - inicio.tv_sec) * 1e6 + (fim.tv_nsec - inicio.tv_nsec) / 1e3;
}


/* --- Interrupcao de Hardware (Etapas 2 e 4) --- */
static bool IRAM_ATTR on_timer_alarm_cb(gptimer_handle_t timer,
                                        const gptimer_alarm_event_data_t *edata,
                                        void *user_ctx) {
    BaseType_t xHigherPriorityTaskWoken = pdFALSE;

#if ETAPA_ATUAL == 2
    /* Etapa 2: acorda a tarefa Huffman a cada evento externo */
    if (sem_evento != NULL) {
        xSemaphoreGiveFromISR(sem_evento, &xHigherPriorityTaskWoken);
    }
#elif ETAPA_ATUAL == 4
    /* Etapa 4: simula rajada de interrupcoes externas (perifericos/rede) */
    esp_rom_delay_us(120);
#endif

    return (xHigherPriorityTaskWoken == pdTRUE);
}


static void iniciar_timer_hw(uint64_t periodo_us) {
    gptimer_handle_t gptimer = NULL;
    gptimer_config_t timer_config = {
        .clk_src = GPTIMER_CLK_SRC_DEFAULT,
        .direction = GPTIMER_COUNT_UP,
        .resolution_hz = 1000000, /* 1 tick = 1 us */
    };
    ESP_ERROR_CHECK(gptimer_new_timer(&timer_config, &gptimer));

    gptimer_event_callbacks_t cbs = {
        .on_alarm = on_timer_alarm_cb,
    };
    ESP_ERROR_CHECK(gptimer_register_event_callbacks(gptimer, &cbs, NULL));
    ESP_ERROR_CHECK(gptimer_enable(gptimer));

    gptimer_alarm_config_t alarm_config = {
        .reload_count = 0,
        .alarm_count = periodo_us,
        .flags.auto_reload_on_alarm = true,
    };
    ESP_ERROR_CHECK(gptimer_set_alarm_action(gptimer, &alarm_config));
    ESP_ERROR_CHECK(gptimer_start(gptimer));
}

/* --- Tarefas Concorrentes (Etapas 3 e 4) --- */

/* Tarefa 1 (Alta Prioridade = 5, Periodo = 4 ms): preempcao + disputa de mutex */
static void tarefa_alta_prioridade(void *arg) {
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xPeriod = pdMS_TO_TICKS(4);

    while (teste_em_andamento) {
        vTaskDelayUntil(&xLastWakeTime, xPeriod);
        if (xSemaphoreTake(mutex_recurso, portMAX_DELAY) == pdTRUE) {
            /* Simula leitura de sensor / escrita rapida no buffer compartilhado */
            buffer_compartilhado[0] ^= 0xFF;
            esp_rom_delay_us(500);
            xSemaphoreGive(mutex_recurso);
        }
    }
    vTaskDelete(NULL);
}

/* Tarefa 3 (Baixa Prioridade = 2, Periodo = 25 ms): causa bloqueio por mutex */
static void tarefa_baixa_prioridade(void *arg) {
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xPeriod = pdMS_TO_TICKS(25);

    while (teste_em_andamento) {
        vTaskDelayUntil(&xLastWakeTime, xPeriod);
        if (xSemaphoreTake(mutex_recurso, portMAX_DELAY) == pdTRUE) {
            /* Simula consolidacao lenta que bloqueia a tarefa Huffman */
            esp_rom_delay_us(1200);
            xSemaphoreGive(mutex_recurso);
        }
    }
    vTaskDelete(NULL);
}

/* Carga Externa de Sistema no Core 0 (Etapa 4): contencao de barramento e cache */
static void tarefa_estresse_sistema_core0(void *arg) {
    uint8_t *arena = (uint8_t *)malloc(65536); /* 64 KB para saturar cache L1 */
    uint32_t ciclos = 0;

    while (teste_em_andamento && arena != NULL) {
        for (int i = 0; i < 65536; i += 32) {
            arena[i] = (uint8_t)(arena[i] + i + ciclos);
        }
        ciclos++;
        /* Cede 1 tick periodicamente para nao disparar o Task Watchdog do Core 0 */
        if ((ciclos % 40) == 0) {
            vTaskDelay(1);
        }
    }
    free(arena);
    vTaskDelete(NULL);
}

/* --- Tarefa Principal Sob Teste: Huffman --- */
static void tarefa_huffman_principal(void *arg) {
    uint8_t *local_buf = (uint8_t *)malloc(TAMANHO_ARRAY);
    struct timespec t_inicio, t_fim;

    srand(SEED_FIXA);

    /* Aguarda estabilizacao da porta serial */
    vTaskDelay(pdMS_TO_TICKS(2000));
    printf("\n=== INICIO_CSV_ETAPA_%d ===\n", ETAPA_ATUAL);
    printf("ativacao,tempo_us\n");

#if (ETAPA_ATUAL == 3) || (ETAPA_ATUAL == 4)
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xPeriod = pdMS_TO_TICKS(15); /* Ativacao periodica a cada 15 ms */
#endif

    for (int i = 1; i <= TOTAL_ATIVACOES; i++) {
        /* Prepara os dados determinísticos da ativação antes do disparo */
        for (size_t j = 0; j < TAMANHO_ARRAY; j++) {
            local_buf[j] = (uint8_t)(rand() % 256);
        }

#if ETAPA_ATUAL == 1
        /* Etapa 1: Execucao isolada */
        clock_gettime(CLOCK_MONOTONIC, &t_inicio);
        int ok = executar_tarefa_huffman(local_buf, TAMANHO_ARRAY);
        clock_gettime(CLOCK_MONOTONIC, &t_fim);

#elif ETAPA_ATUAL == 2
        /* Etapa 2: Aguarda interrupcao externa (1 evento por vez) */
        xSemaphoreTake(sem_evento, portMAX_DELAY);
        clock_gettime(CLOCK_MONOTONIC, &t_inicio);
        int ok = executar_tarefa_huffman(local_buf, TAMANHO_ARRAY);
        clock_gettime(CLOCK_MONOTONIC, &t_fim);

#elif (ETAPA_ATUAL == 3) || (ETAPA_ATUAL == 4)
        /* Etapas 3 e 4: Ativacao periodica + disputa de mutex + preempcao */
        vTaskDelayUntil(&xLastWakeTime, xPeriod);

        clock_gettime(CLOCK_MONOTONIC, &t_inicio);
        xSemaphoreTake(mutex_recurso, portMAX_DELAY);
        memcpy(buffer_compartilhado, local_buf, TAMANHO_ARRAY);
        xSemaphoreGive(mutex_recurso);

        int ok = executar_tarefa_huffman(local_buf, TAMANHO_ARRAY);
        clock_gettime(CLOCK_MONOTONIC, &t_fim);
#endif

        if (!ok) {
            printf("ERRO_VALIDACAO,%d\n", i);
            break;
        }

        double tempo_us = calcular_tempo_us(t_inicio, t_fim);
        printf("%d,%.3f\n", i, tempo_us);

#if ETAPA_ATUAL == 1
        /* Evita disparo do Task Watchdog em 10.000 iteracoes seguidas */
        if ((i % 25) == 0) {
            vTaskDelay(1);
        }
#endif
    }

    printf("=== FIM_CSV_ETAPA_%d ===\n", ETAPA_ATUAL);
    teste_em_andamento = false;
    free(local_buf);
    vTaskDelete(NULL);
}

void app_main(void) {
    /* Silencia logs internos do ESP-IDF para manter a saida serial limpa */
    esp_log_level_set("*", ESP_LOG_NONE);

#if ETAPA_ATUAL == 1
    xTaskCreatePinnedToCore(tarefa_huffman_principal, "huffman", 8192, NULL, 3, NULL, 1);

#elif ETAPA_ATUAL == 2
    sem_evento = xSemaphoreCreateBinary();
    xTaskCreatePinnedToCore(tarefa_huffman_principal, "huffman", 8192, NULL, 3, NULL, 1);
    iniciar_timer_hw(15000); /* 1 interrupcao a cada 15 ms */

#elif ETAPA_ATUAL == 3
    mutex_recurso = xSemaphoreCreateMutex();
    xTaskCreatePinnedToCore(tarefa_alta_prioridade,   "t_alta",  4096, NULL, 5, NULL, 1);
    xTaskCreatePinnedToCore(tarefa_huffman_principal, "huffman", 8192, NULL, 3, NULL, 1);
    xTaskCreatePinnedToCore(tarefa_baixa_prioridade,  "t_baixa", 4096, NULL, 2, NULL, 1);

#elif ETAPA_ATUAL == 4
    mutex_recurso = xSemaphoreCreateMutex();
    xTaskCreatePinnedToCore(tarefa_estresse_sistema_core0, "stress_c0", 4096, NULL, 4, NULL, 0);
    xTaskCreatePinnedToCore(tarefa_alta_prioridade,        "t_alta",    4096, NULL, 5, NULL, 1);
    xTaskCreatePinnedToCore(tarefa_huffman_principal,      "huffman",   8192, NULL, 3, NULL, 1);
    xTaskCreatePinnedToCore(tarefa_baixa_prioridade,       "t_baixa",   4096, NULL, 2, NULL, 1);
    iniciar_timer_hw(500); /* Interrupcao externa a 2 kHz (a cada 500 us) */
#endif
}