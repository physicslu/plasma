"""Host-only entry point for the shared low-density evidence validator."""
from plasma_web.stm32f103_low_density_candidate import audit_candidate

if __name__ == "__main__":
    import json
    print(json.dumps(audit_candidate(), indent=2, sort_keys=True))
