#ifndef HUFFMAN_H
#define HUFFMAN_H

#include <stddef.h>
#include <stdint.h>

/* Codifica, decodifica e valida a integridade dos dados.
 
Retorna 1 se a validacao passou, 0 caso contrario. */
int executar_tarefa_huffman(const uint8_t *entrada, size_t n);

#endif