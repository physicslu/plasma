#include "main.h"
#include "app.h"
#include "usbd_desc.h"

static USBD_HandleTypeDef usb_device;
extern volatile uint32_t usb_epoch;
static app_t app;
static uint8_t rx_packet[64];
static uint8_t line_coding[7] = {0x00, 0xC2, 0x01, 0x00, 0, 0, 8}; /* 115200 8N1 */
/* This buffer is never modified while CDC TxState is nonzero. */
static char tx_packet[APP_TX_CAPACITY];

static int8_t cdc_init(void) {
    USBD_CDC_SetTxBuffer(&usb_device, (uint8_t *)tx_packet, 0);
    USBD_CDC_SetRxBuffer(&usb_device, rx_packet);
    return USBD_OK;
}

static int8_t cdc_deinit(void) { return USBD_OK; }

static int8_t cdc_control(uint8_t command, uint8_t *buffer, uint16_t length) {
    if (command == CDC_SET_LINE_CODING && length == sizeof(line_coding))
        memcpy(line_coding, buffer, sizeof(line_coding));
    if (command == CDC_GET_LINE_CODING && length == sizeof(line_coding))
        memcpy(buffer, line_coding, sizeof(line_coding));
    return USBD_OK;
}

static int8_t cdc_receive(uint8_t *buffer, uint32_t *length) {
    app_receive_irq(&app, buffer, *length);
    USBD_CDC_SetRxBuffer(&usb_device, rx_packet);
    return (int8_t)USBD_CDC_ReceivePacket(&usb_device);
}

static USBD_CDC_ItfTypeDef cdc_ops = {
    cdc_init, cdc_deinit, cdc_control, cdc_receive
};

static void system_clock_config(void) {
    RCC_OscInitTypeDef oscillator = {0};
    RCC_ClkInitTypeDef clock = {0};
    RCC_PeriphCLKInitTypeDef peripheral = {0};
    oscillator.OscillatorType = RCC_OSCILLATORTYPE_HSE;
    oscillator.HSEState = RCC_HSE_ON;
    oscillator.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
    oscillator.PLL.PLLState = RCC_PLL_ON;
    oscillator.PLL.PLLSource = RCC_PLLSOURCE_HSE;
    oscillator.PLL.PLLMUL = RCC_PLL_MUL9;
    if (HAL_RCC_OscConfig(&oscillator) != HAL_OK) Error_Handler();
    clock.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK |
                      RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    clock.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    clock.AHBCLKDivider = RCC_SYSCLK_DIV1;
    clock.APB1CLKDivider = RCC_HCLK_DIV2;
    clock.APB2CLKDivider = RCC_HCLK_DIV1;
    if (HAL_RCC_ClockConfig(&clock, FLASH_LATENCY_2) != HAL_OK) Error_Handler();
    peripheral.PeriphClockSelection = RCC_PERIPHCLK_USB;
    peripheral.UsbClockSelection = RCC_USBCLKSOURCE_PLL_DIV1_5;
    if (HAL_RCCEx_PeriphCLKConfig(&peripheral) != HAL_OK) Error_Handler();
}

static void led_init(void) {
    __HAL_RCC_GPIOC_CLK_ENABLE();
    /* Preload active-low ON before switching to output. No tick dependency. */
    HAL_GPIO_WritePin(GPIOC, GPIO_PIN_13, GPIO_PIN_RESET);
    GPIO_InitTypeDef led = {0};
    led.Pin = GPIO_PIN_13;
    led.Mode = GPIO_MODE_OUTPUT_PP;
    led.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOC, &led);
}

int main(void) {
    led_init();
    if (HAL_Init() != HAL_OK) Error_Handler();
    system_clock_config();
    app_init(&app);
    app.led_last_ms = HAL_GetTick();
    if (USBD_Init(&usb_device, &VCP_Desc, 0) != USBD_OK ||
        USBD_RegisterClass(&usb_device, USBD_CDC_CLASS) != USBD_OK ||
        USBD_CDC_RegisterInterface(&usb_device, &cdc_ops) != USBD_OK ||
        USBD_Start(&usb_device) != USBD_OK) Error_Handler();
    uint32_t seen_epoch = usb_epoch;
    for (;;) {
        uint32_t now = HAL_GetTick();
        if (seen_epoch != usb_epoch) {
            seen_epoch = usb_epoch;
            app_link(&app, false, now);
        }
        bool configured = usb_device.dev_state == USBD_STATE_CONFIGURED &&
                          usb_device.pClassData != NULL;
        app_link(&app, configured, now);
        app_process(&app, now);
        HAL_GPIO_WritePin(GPIOC, GPIO_PIN_13,
                          app.led_on ? GPIO_PIN_RESET : GPIO_PIN_SET);
        if (configured && ((USBD_CDC_HandleTypeDef *)usb_device.pClassData)->TxState == 0U) {
            bool heartbeat = false;
            size_t length = app_next(&app, now, tx_packet, sizeof(tx_packet), &heartbeat);
            if (length != 0U) {
                __disable_irq();
                if (seen_epoch == usb_epoch &&
                    usb_device.dev_state == USBD_STATE_CONFIGURED &&
                    usb_device.pClassData != NULL &&
                    ((USBD_CDC_HandleTypeDef *)usb_device.pClassData)->TxState == 0U) {
                    USBD_CDC_SetTxBuffer(&usb_device, (uint8_t *)tx_packet, (uint16_t)length);
                    if (USBD_CDC_TransmitPacket(&usb_device) == USBD_OK)
                        app_sent(&app, now, heartbeat);
                }
                __enable_irq();
            }
        }
    }
}

void SysTick_Handler(void) { HAL_IncTick(); }
void USB_LP_CAN1_RX0_IRQHandler(void) { extern PCD_HandleTypeDef hpcd; HAL_PCD_IRQHandler(&hpcd); }
/* Approximate timing only: works on HSI or PLL, with interrupts stopped. */
static void fault_pause(uint32_t units) {
    for (uint32_t i = 0; i < units; ++i)
        for (volatile uint32_t n = 0; n < 150000u; ++n) __NOP();
}

void Error_Handler(void) {
    __disable_irq();
    led_init();
    for (;;) {
        /* Repeating double flash then a long dark gap; never HAL_Delay. */
        for (unsigned pulse = 0; pulse < 2; ++pulse) {
            HAL_GPIO_WritePin(GPIOC, GPIO_PIN_13, GPIO_PIN_RESET);
            fault_pause(1);
            HAL_GPIO_WritePin(GPIOC, GPIO_PIN_13, GPIO_PIN_SET);
            fault_pause(1);
        }
        fault_pause(8);
    }
}
void _init(void) {}
void _fini(void) {}
