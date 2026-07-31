class CommandHelpComponent:
    template_name = "components/search2/command_help.html"

    class Media:
        js = ["search2/command_help.js"]

    def get_context_data(self, *args, **kwargs):
        from search2.apps import generate_command_help_rows

        return {"help_rows": generate_command_help_rows()}
