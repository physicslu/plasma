"""Source integration guards; these do not execute an MCU or prove USB enumeration."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StartupContract(unittest.TestCase):
    def test_early_led_and_nonblocking_loop(self):
        source = (ROOT / 'src/main.c').read_text()
        main = source.split('int main(void) {', 1)[1]
        self.assertLess(main.index('led_init();'), main.index('HAL_Init()'))
        self.assertLess(main.index('led_init();'), main.index('system_clock_config();'))
        self.assertLess(main.index('app_init(&app);'), main.index('USBD_Init('))
        loop = main.split('for (;;) {', 1)[1].split('void SysTick_Handler', 1)[0]
        self.assertLess(loop.index('app_process(&app, now);'), loop.index('if (configured &&'))
        self.assertNotIn('HAL_Delay(', loop)

    def test_boot_disconnect_is_bounded_released_and_before_usb(self):
        source = (ROOT / 'src/main.c').read_text()
        pulse = source.split('static void usb_boot_disconnect(void) {', 1)[1].split('static void led_init', 1)[0]
        steps = [
            'if (__HAL_RCC_USB_IS_CLK_ENABLED()) Error_Handler();',
            '__HAL_RCC_GPIOA_CLK_ENABLE();',
            'HAL_GPIO_WritePin(GPIOA, GPIO_PIN_12, GPIO_PIN_RESET);',
            'dp.Pin = GPIO_PIN_12;', 'dp.Mode = GPIO_MODE_OUTPUT_OD;',
            'HAL_GPIO_Init(GPIOA, &dp);', 'HAL_Delay(30);',
            'dp.Mode = GPIO_MODE_INPUT;', 'dp.Pull = GPIO_NOPULL;',
            'HAL_GPIO_Init(GPIOA, &dp);',
        ]
        cursor = 0
        for step in steps:
            cursor = pulse.index(step, cursor) + len(step)
        self.assertEqual(pulse.count('HAL_Delay('), 1)
        self.assertNotIn('GPIO_PIN_SET', pulse)
        for forbidden in ('GPIO_PIN_11', 'GPIO_PIN_13', 'GPIO_PIN_14',
                          'REMAP', 'USB_CLK_ENABLE', 'for (', 'while ('):
            self.assertNotIn(forbidden, pulse)
        main = source.split('int main(void) {', 1)[1]
        self.assertLess(main.index('HAL_Init()'), main.index('usb_boot_disconnect();'))
        self.assertLess(main.index('system_clock_config();'), main.index('usb_boot_disconnect();'))
        self.assertLess(main.index('usb_boot_disconnect();'), main.index('USBD_Init('))
        self.assertEqual(source.count('usb_boot_disconnect();'), 1)
        self.assertNotIn('usb_boot_disconnect', main.split('for (;;) {', 1)[1])
        msp = (ROOT / 'src/usbd_conf.c').read_text().split('void HAL_PCD_MspInit', 1)[1].split('void HAL_PCD_MspDeInit', 1)[0]
        self.assertLess(msp.index('HAL_GPIO_Init(GPIOA'), msp.index('__HAL_RCC_USB_CLK_ENABLE();'))

    def test_fault_has_no_interrupt_or_tick_dependency(self):
        source = (ROOT / 'src/main.c').read_text()
        fault = source.split('static void fault_pause(', 1)[1]
        for forbidden in ('HAL_Delay(', 'HAL_GetTick(', '__enable_irq('):
            self.assertNotIn(forbidden, fault)
        self.assertIn('volatile uint32_t n', fault)
        self.assertIn('__disable_irq();', fault)
        self.assertIn('pulse < 2', fault)
        self.assertIn('fault_pause(8);', fault)

    def test_ignored_usb_failures_reach_fault_handler(self):
        source = (ROOT / 'src/usbd_conf.c').read_text()
        init = source.split('USBD_StatusTypeDef USBD_LL_Init(', 1)[1].split('USBD_StatusTypeDef USBD_LL_DeInit', 1)[0]
        self.assertEqual(init.count('return USBD_FAIL;'), 2)
        self.assertEqual(init.count('Error_Handler();'), 2)
        start = source.split('USBD_StatusTypeDef USBD_LL_Start(', 1)[1].split('USBD_StatusTypeDef USBD_LL_Stop', 1)[0]
        self.assertIn('!= HAL_OK)', start)
        self.assertLess(start.index('Error_Handler();'), start.index('return USBD_FAIL;'))


if __name__ == '__main__':
    unittest.main()
