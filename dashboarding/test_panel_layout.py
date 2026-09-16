from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from dashboarding.models import Dashboard, Panel
from dashboarding.views import build_panel_data


class PanelLayoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='layout-owner')
        self.dashboard = Dashboard.objects.create(name='Layout', created_by=self.user)

    def test_rows_sort_columns_and_keep_layout_for_empty_and_failed_searches(self):
        right = Panel.objects.create(dashboard=self.dashboard, row=2, column=9, search='bad')
        top = Panel.objects.create(dashboard=self.dashboard, row=1, column=5)
        left = Panel.objects.create(dashboard=self.dashboard, row=2, column=2, search='good')
        with patch('dashboarding.views.run_pipeline', side_effect=[[{'value': 1}], ValueError('bad')]):
            items = build_panel_data(self.dashboard, {}, None)
        self.assertEqual([item['panel'].pk for item in items], [top.pk, left.pk, right.pk])
        self.assertEqual([item['col_span'] for item in items], [12, 6, 6])
        self.assertEqual([item['row_start'] for item in items], [True, True, False])
        self.assertIsNone(items[0]['data'])
        self.assertEqual(items[1]['data'], [{'value': 1}])
        self.assertEqual(items[2]['error'], 'bad')

    def test_all_sibling_counts_have_expected_widths(self):
        for count, span in enumerate([12, 6, 4, 3, 2, 2, 1, 1, 1, 1, 1, 1, 1], start=1):
            with self.subTest(count=count):
                self.dashboard.panels.all().delete()
                Panel.objects.bulk_create([Panel(dashboard=self.dashboard) for _ in range(count)])
                items = build_panel_data(self.dashboard, {}, None)
                self.assertEqual([item['col_span'] for item in items], [span] * count)
                self.assertEqual([item['row_start'] for item in items], [True] + [False] * (count - 1))

    def test_template_groups_rows_and_keeps_mobile_columns_full_width(self):
        Panel.objects.create(dashboard=self.dashboard, row=1)
        Panel.objects.create(dashboard=self.dashboard, row=2, column=1)
        Panel.objects.create(dashboard=self.dashboard, row=2, column=2)
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboarding:dashboard_detail', args=[self.dashboard.pk]))
        self.assertContains(response, '<div class="row">', count=2)
        self.assertContains(response, '<div class="col-12 mb-4">', count=1)
        self.assertContains(response, '<div class="col-12 col-lg-6 mb-4">', count=2)
        self.assertContains(response, '<div class="card h-100">', count=3)


class PanelPositionMigrationTests(TransactionTestCase):
    def test_existing_dashboards_keep_one_panel_per_row_in_old_order(self):
        before = [('dashboarding', '0003_dashboard_shared')]
        after = [('dashboarding', '0005_backfill_panel_positions')]
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        try:
            apps = executor.loader.project_state(before).apps
            User = apps.get_model(*get_user_model()._meta.label.split('.'))
            Dashboard = apps.get_model('dashboarding', 'Dashboard')
            Panel = apps.get_model('dashboarding', 'Panel')
            user = User.objects.create(username='migration-owner')
            expected = {}
            for name, orders in [('Zero trust evidence', [8, 2, 2, 0]), ('Other', [5, 1]), ('Empty', [])]:
                dashboard = Dashboard.objects.create(name=name, created_by=user)
                for order in orders:
                    Panel.objects.create(dashboard=dashboard, order=order)
                expected[dashboard.pk] = list(
                    Panel.objects.filter(dashboard=dashboard).order_by('order', 'id').values_list('id', 'order')
                )
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            Panel = executor.loader.project_state(after).apps.get_model('dashboarding', 'Panel')
            for dashboard_id, old_panels in expected.items():
                self.assertEqual(
                    list(Panel.objects.filter(dashboard_id=dashboard_id).values_list('id', 'order', 'row', 'column')),
                    [(pk, order, index, 1) for index, (pk, order) in enumerate(old_panels, start=1)],
                )
        finally:
            MigrationExecutor(connection).migrate(after)
