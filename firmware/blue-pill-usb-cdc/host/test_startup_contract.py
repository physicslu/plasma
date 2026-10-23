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
