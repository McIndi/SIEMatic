from django.db import migrations


def backfill_row_column(apps, schema_editor):
    Dashboard = apps.get_model('dashboarding', 'Dashboard')
    Panel = apps.get_model('dashboarding', 'Panel')
    alias = schema_editor.connection.alias
    for dashboard in Dashboard.objects.using(alias).all():
        # Preserve the old display order, including ties, regardless of Meta.
        panels = Panel.objects.using(alias).filter(dashboard=dashboard).order_by('order', 'id')
        for index, panel in enumerate(panels, start=1):
            panel.row = index
            panel.column = 1
            panel.save(using=alias, update_fields=['row', 'column'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('dashboarding', '0004_alter_panel_options_panel_column_panel_row'),
    ]

    operations = [
        migrations.RunPython(backfill_row_column, noop_reverse),
    ]
