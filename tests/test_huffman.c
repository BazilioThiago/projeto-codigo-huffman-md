#include <assert.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdio.h>
static int fail_at=-1, allocations;
static void *test_malloc(size_t n) { return allocations++ == fail_at ? NULL : malloc(n); }
static void *test_calloc(size_t n,size_t s) { return allocations++ == fail_at ? NULL : calloc(n,s); }
#define malloc test_malloc
#define calloc test_calloc
#include "../main/huffman.c"
#undef malloc
#undef calloc
int main(void) {
    uint8_t data[4096];
    assert(executar_tarefa_huffman(NULL,0));
    assert(!executar_tarefa_huffman(NULL,1));
#if SIZE_MAX > UINT32_MAX
    assert(!executar_tarefa_huffman(data,(size_t)UINT32_MAX+1));
#endif
    memset(data,42,sizeof(data));
    assert(executar_tarefa_huffman(data,sizeof(data)));
    for (int i=0;i<4096;i++) data[i]=(uint8_t)i;
    allocations=0;
    assert(executar_tarefa_huffman(data,sizeof(data)));
    int total=allocations;
    for (int i=0;i<total;i++) {
        allocations=0; fail_at=i;
        assert(!executar_tarefa_huffman(data,sizeof(data)));
    }
    fail_at=-1;
    srand(42);
    for (int n=1;n<=4096;n+=7) {
        for (int i=0;i<n;i++) data[i]=(uint8_t)(rand()%256);
        assert(executar_tarefa_huffman(data,n));
    }
    puts("OK: empty, invalid, singleton, all symbols, random sizes and all allocation failures");
    return 0;
}
