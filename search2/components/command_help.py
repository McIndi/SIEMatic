import argparse

class CommandHelpComponent:
    template_name = "components/search2/command_help.html"

    class Media:
        js = ["search2/command_help.js"]

    def get_context_data(self, *args, **kwargs):
        import logging
        logger = logging.getLogger(__name__)
        from search2.apps import _COMMANDS
        help_rows = []
        logger.info(f"Loaded commands: {list(_COMMANDS.keys())}")
        for name, cmd in _COMMANDS.items():
            logger.info(f"Processing command: {name} ({cmd.__class__.__name__})")
            add_args = getattr(cmd, "add_arguments", None)
            if not callable(add_args):
                logger.warning(f"Command '{name}' missing add_arguments method.")
                continue
            parser = argparse.ArgumentParser(prog=name)
            add_args(parser)
            logger.info(f"Arguments for '{name}': {[a.dest for a in parser._actions]}")
            arg_list = []
            for action in parser._actions:
                logger.debug(f"Action: dest={action.dest}, opts={action.option_strings}, type={action.type}, default={action.default}, help={action.help}")
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
                    "help": action.help or ""
                })
            help_rows.append({
                "command": name,
                "description": getattr(cmd, "__doc__", ""),
                "arguments": arg_list,
            })
        logger.info(f"Total help rows generated: {len(help_rows)}")
        return {"help_rows": help_rows}
