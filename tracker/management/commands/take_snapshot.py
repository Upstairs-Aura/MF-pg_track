from django.core.management.base import BaseCommand
from django.utils import timezone

from tracker.models import Location, ScopeHeading, Task, DailySnapshot
from tracker.views import task_color, compute_location_stats


class Command(BaseCommand):
    help = "Freezes the current state of every location/heading/task into a DailySnapshot row."

    def handle(self, *args, **options):
        today = timezone.localdate()

        if DailySnapshot.objects.filter(snapshot_date=today).exists():
            self.stdout.write(self.style.WARNING(f"Snapshot for {today} already exists — skipping."))
            return

        data = {"locations": []}

        for location in Location.objects.all():
            compute_location_stats(location)
            location_data = {
                "id": location.id,
                "name": location.name,
                "is_archived": location.is_archived,
                "percent_complete": location.percent_complete,
                "overdue_count": location.overdue_count,
                "at_risk_count": location.at_risk_count,
                "status_color": location.status_color,
                "headings": [],
            }

            for heading in ScopeHeading.objects.filter(location=location):
                heading_label = heading.custom_label if heading.heading_name == "custom" else heading.get_heading_name_display()
                heading_data = {
                    "heading_name": heading.heading_name,
                    "label": heading_label,
                    "tasks": [],
                }

                for task in Task.objects.filter(heading=heading):
                    heading_data["tasks"].append({
                        "id": task.id,
                        "name": task.name,
                        "task_type": task.task_type,
                        "assignee": task.assignee.name if task.assignee else None,
                        "start_date": str(task.start_date),
                        "end_date": str(task.end_date),
                        "actual_end_date": str(task.actual_end_date) if task.actual_end_date else None,
                        "status": task.status,
                        "doc_status": task.doc_status,
                        "funds_type": task.funds_type,
                        "funds_amount": str(task.funds_amount) if task.funds_amount else None,
                        "color": task_color(task),
                    })

                location_data["headings"].append(heading_data)

            data["locations"].append(location_data)

        DailySnapshot.objects.create(snapshot_date=today, data=data)
        self.stdout.write(self.style.SUCCESS(f"Snapshot for {today} saved."))