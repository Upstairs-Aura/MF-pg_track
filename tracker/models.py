from django.db import models


class Manager(models.Model):
    staff_id = models.CharField(max_length=20, unique=True)
    password_hash = models.CharField(max_length=255)
    name = models.CharField(max_length=100)
    department = models.ForeignKey("Department", on_delete=models.SET_NULL, null=True, blank=True, related_name="staff")
    is_admin = models.BooleanField(default=False)
    last_login_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    is_active_session = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Department(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Location(models.Model):
    name = models.CharField(max_length=150)
    created_at = models.DateField(auto_now_add=True)
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    department = models.ForeignKey("Department", on_delete=models.SET_NULL, null=True, blank=True, related_name="owned_locations")
    shared_with_managers = models.ManyToManyField(Manager, related_name="shared_locations", blank=True)

    def __str__(self):
        return self.name


class ScopeHeading(models.Model):
    HEADING_CHOICES = [
        ("branding", "Branding"),
        ("construction", "Construction"),
        ("electrical", "Electrical"),
        ("operation", "Operation"),
        ("safety", "Safety"),
        ("regulatory_documents", "Regulatory Documents"),
        ("custom", "Custom"),
    ]
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="scope_headings")
    heading_name = models.CharField(max_length=30, choices=HEADING_CHOICES)
    custom_label = models.CharField(max_length=100, null=True, blank=True)
    departments = models.ManyToManyField(Department, related_name="scope_headings", blank=True)

    def __str__(self):
        return f"{self.location.name} · {self.get_heading_name_display()}"


class Task(models.Model):
    TASK_TYPE_CHOICES = [
        ("normal", "Normal"),
        ("regulatory_doc", "Regulatory Document"),
        ("action_point", "Action Point"),
    ]
    STATUS_CHOICES = [
        ("not_done", "Not Done"),
        ("in_progress", "In Progress"),
        ("done", "Done"),
    ]
    DOC_STATUS_CHOICES = [
        ("received", "Received"),
        ("waiting_approval", "Waiting Approval"),
        ("sent_approved", "Sent and Approved"),
    ]
    FUNDS_TYPE_CHOICES = [
        ("na", "N/A"),
        ("none", "None"),
        ("amount", "Amount"),
    ]

    heading = models.ForeignKey(ScopeHeading, on_delete=models.CASCADE, related_name="tasks")
    parent_task = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="action_points")
    task_type = models.CharField(max_length=20, choices=TASK_TYPE_CHOICES, default="normal")
    name = models.CharField(max_length=200)
    assignee = models.ForeignKey(Manager, on_delete=models.SET_NULL, null=True, related_name="tasks")
    start_date = models.DateField()
    end_date = models.DateField()
    actual_end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="not_done")
    doc_status = models.CharField(max_length=20, choices=DOC_STATUS_CHOICES, null=True, blank=True)
    funds_type = models.CharField(max_length=10, choices=FUNDS_TYPE_CHOICES, default="na")
    funds_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return self.name


class Remark(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="remarks")
    author = models.ForeignKey(Manager, on_delete=models.SET_NULL, null=True)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.author}: {self.text[:30]}"


class AuditLogEntry(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="audit_log")
    field_changed = models.CharField(max_length=50)
    old_value = models.CharField(max_length=255, blank=True)
    new_value = models.CharField(max_length=255, blank=True)
    changed_by = models.ForeignKey(Manager, on_delete=models.SET_NULL, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)


class DailySnapshot(models.Model):
    snapshot_date = models.DateField(unique=True)
    data = models.JSONField()

    def __str__(self):
        return str(self.snapshot_date)


class ManagerDepartment(models.Model):
    manager = models.ForeignKey(Manager, on_delete=models.CASCADE)
    department = models.ForeignKey(Department, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("manager", "department")

class PasswordResetLog(models.Model):
    manager = models.ForeignKey(Manager, on_delete=models.CASCADE, related_name="password_resets")
    reset_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.manager.staff_id} reset at {self.reset_at}"