from importlib import import_module
from django.conf import settings
from django.apps import AppConfig

# Removed dependency on django_components; we no longer register template components.


_COMMANDS: dict[str, object] = {}

def get_command(name: str):
    try:
        return _COMMANDS[name]
    except KeyError:
        raise ValueError(f"Unknown command: {name}")

class Search2Config(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'search2'

    def ready(self):
        # Previously, django-components were used to register UI components.
        # To avoid the rust dependency, we no longer register components here.

        # Register search commands
        cfg = getattr(settings, "SIEMATIC_SEARCH", {})
        for spec in cfg.get("COMMANDS", []):
            # support "pkg.mod:ClassName" or "pkg.mod.ClassName"
            mod, cls = (spec.split(":") if ":" in spec else spec.rsplit(".", 1))
            modobj = import_module(mod)
            klass = getattr(modobj, cls)
            inst = klass()
            name = getattr(inst, "name", None)
            if not name:
                raise RuntimeError(f"{spec} missing .name")
            _COMMANDS[name] = inst


def generate_command_help_rows():
    """
    Generate a list of command help rows from registered search commands.
    Returns a list of dicts suitable for rendering in templates.
    """
    import argparse
    help_rows = []
    for name, cmd in _COMMANDS.items():
        add_args = getattr(cmd, "add_arguments", None)
        if not callable(add_args):
            continue
        parser = argparse.ArgumentParser(prog=name)
        try:
            add_args(parser)
        except Exception:
            # If add_arguments raises, skip this command
            continue
        arg_list = []
        for action in parser._actions:
            if action.dest == 'help':
                continue
            if action.type is None:
                type_str = "str"
            elif hasattr(action.type, "__name__"):
                type_str = action.type.__name__
            else:
                type_str = str(action.type)
            arg_list.append({
                "flag": action.option_strings[0] if action.option_strings else action.dest,
                "type": type_str,
                "default": action.default,
                "help": action.help or "",
            })
        help_rows.append({
            "command": name,
            "description": getattr(cmd, "__doc__", ""),
            "arguments": arg_list,
        })
    return help_rows
