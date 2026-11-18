idf_component_register(
    SRCS "main.c" "huffman.c"
    INCLUDE_DIRS "."
    REQUIRES esp_driver_gptimer spi_flash esp_timer
)