import os
import importlib.util

def load_handler_map(handler_dir):
    handler_map = {}
    for filename in os.listdir(handler_dir):
        if filename.startswith("ic_") and filename.endswith(".py"):
            module_name = filename[:-3]
            file_path = os.path.join(handler_dir, filename)
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "handler_map"):
                handler_map.update(module.handler_map)
    return handler_map

