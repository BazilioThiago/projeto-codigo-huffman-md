#include "huffman.h"
#include <stdlib.h>
#include <string.h>

typedef struct Node {
    uint8_t symbol;
    uint32_t freq;
    struct Node *left;
    struct Node *right;
} Node;

typedef struct {
    Node *data[256];
    int size;
} MinHeap;

typedef struct {
    uint8_t bits[256];
    int length;
} HuffmanCode;

static Node *create_node(uint8_t symbol, uint32_t freq, Node *left, Node *right) {
    Node *n = (Node *)malloc(sizeof(Node));
    if (!n) return NULL;
    n->symbol = symbol;
    n->freq = freq;
    n->left = left;
    n->right = right;
    return n;
}

static void heap_push(MinHeap *h, Node *n) {
    int i = h->size++;
    while (i > 0) {
        int parent = (i - 1) / 2;
        if (h->data[parent]->freq <= n->freq) break;
        h->data[i] = h->data[parent];
        i = parent;
    }
    h->data[i] = n;
}

static Node *heap_pop(MinHeap *h) {
    Node *min = h->data[0];
    Node *last = h->data[--h->size];
    int i = 0;
    while (i * 2 + 1 < h->size) {
        int child = i * 2 + 1;
        if (child + 1 < h->size && h->data[child + 1]->freq < h->data[child]->freq) {
            child++;
        }
        if (last->freq <= h->data[child]->freq) break;
        h->data[i] = h->data[child];
        i = child;
    }
    if (h->size > 0) h->data[i] = last;
    return min;
}

static void build_codes(Node *root, HuffmanCode *codes, uint8_t *path, int depth) {
    if (!root->left && !root->right) {
        if (depth == 0) {
            codes[root->symbol].bits[0] = 0;
            codes[root->symbol].length = 1;
        } else {
            memcpy(codes[root->symbol].bits, path, depth);
            codes[root->symbol].length = depth;
        }
        return;
    }
    path[depth] = 0;
    build_codes(root->left, codes, path, depth + 1);
    path[depth] = 1;
    build_codes(root->right, codes, path, depth + 1);
}

static void free_tree(Node *root) {
    if (!root) return;
    free_tree(root->left);
    free_tree(root->right);
    free(root);
}

int executar_tarefa_huffman(const uint8_t *entrada, size_t n) {
    if (n == 0) return 1;
    if (!entrada || n > UINT32_MAX) return 0;
    uint32_t freq[256] = {0};
    for (size_t i = 0; i < n; i++) {
        freq[entrada[i]]++;
    }

    MinHeap *heap = (MinHeap *)calloc(1, sizeof(MinHeap));
    HuffmanCode *codes = (HuffmanCode *)calloc(256, sizeof(HuffmanCode));
    uint8_t *path = (uint8_t *)malloc(256);

    if (!heap || !codes || !path) {
        free(heap);
        free(codes);
        free(path);
        return 0;
    }

    for (int i = 0; i < 256; i++) {
        if (freq[i] > 0) {
            Node *node = create_node((uint8_t)i, freq[i], NULL, NULL);
            if (!node) goto fail_heap;
            heap_push(heap, node);
        }
    }

    while (heap->size > 1) {
        Node *left = heap_pop(heap);
        Node *right = heap_pop(heap);
        Node *node = create_node(0, left->freq + right->freq, left, right);
        if (!node) { free_tree(left); free_tree(right); goto fail_heap; }
        heap_push(heap, node);
    }

    Node *root = heap_pop(heap);
    build_codes(root, codes, path, 0);

    /* 1. Codificacao */
    size_t total_bits = 0;
    for (size_t i = 0; i < n; i++) {
        total_bits += codes[entrada[i]].length;
    }

    size_t encoded_bytes = (total_bits + 7) / 8;
    uint8_t *codificado = (uint8_t *)calloc(encoded_bytes, 1);
    if (!codificado) { free_tree(root); goto fail_heap; }
    size_t bit_pos = 0;

    for (size_t i = 0; i < n; i++) {
        HuffmanCode *c = &codes[entrada[i]];
        for (int b = 0; b < c->length; b++) {
            if (c->bits[b]) {
                codificado[bit_pos >> 3] |= (uint8_t)(1U << (7 - (bit_pos & 7)));
            }
            bit_pos++;
        }
    }

    /* 2. Decodificacao */
    uint8_t *decodificado = (uint8_t *)malloc(n);
    if (!decodificado) { free(codificado); free_tree(root); goto fail_heap; }
    if (!root->left && !root->right) {
        memset(decodificado, root->symbol, n);
    } else {
        Node *curr = root;
        size_t out_idx = 0;
        for (size_t b = 0; b < total_bits; b++) {
            int bit = (codificado[b >> 3] >> (7 - (b & 7))) & 1;
            curr = bit ? curr->right : curr->left;
            if (!curr->left && !curr->right) {
                decodificado[out_idx++] = curr->symbol;
                curr = root;
            }
        }
    }

    /* 3. Validacao logica */
    int valido = (memcmp(entrada, decodificado, n) == 0);

    free(codificado);
    free(decodificado);
    free_tree(root);
    free(heap);
    free(codes);
    free(path);

    return valido;

fail_heap:
    while (heap->size) free_tree(heap_pop(heap));
    free(heap);
    free(codes);
    free(path);
    return 0;
}