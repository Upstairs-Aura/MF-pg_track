from datetime import date

from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone
from datetime import timedelta

from .models import Manager, Location, ScopeHeading, Task, Remark, AuditLogEntry, PasswordResetLog, DailySnapshot

from django.db import models

from django.template.loader import render_to_string
from django.http import HttpResponse
from weasyprint import HTML
from docx import Document
from docx.shared import Pt, RGBColor
from io import BytesIO
# from xhtml2 import pisa

from io import BytesIO
from .report_theme import get_report_theme, hex_to_rgb
#colors for report

HEADING_ORDER = [
    "branding", "construction", "electrical", "operation",
    "safety", "regulatory_documents",
]

def get_heading(location, heading_slug):
    if heading_slug.startswith("custom-"):
        heading_id = heading_slug.split("-", 1)[1]
        return get_object_or_404(ScopeHeading, location=location, id=heading_id, heading_name="custom")
    return get_object_or_404(ScopeHeading, location=location, heading_name=heading_slug)

# ---------------------------------------------------------------
# Item 3 — Red / Yellow / Green + % complete logic
# ---------------------------------------------------------------

def task_color(task):
    today = date.today()
    if task.status == "done":
        if task.actual_end_date and task.actual_end_date <= task.end_date:
            return "green"
        return "red"  # done but late

    if today > task.end_date:
        return "red"  # overdue, not done

    duration = (task.end_date - task.start_date).days
    elapsed = (today - task.start_date).days
    pct_time = max(0.0, elapsed / duration) if duration > 0 else 1.0

    if task.status == "not_done" and pct_time >= 0.75:
        return "red"
    if pct_time >= 0.5:
        return "yellow"
    return "green"


def worst_color(colors):
    if "red" in colors:
        return "red"
    if "yellow" in colors:
        return "yellow"
    return "green"


def initials_for(name):
    parts = name.split()
    return "".join(p[0] for p in parts[:2]).upper() if parts else "?"


def get_online_managers():
    # depends on login (item 1) actually setting is_active_session — will be
    # empty until that's built. Safe to call now, just won't show anyone yet.
    return [
        {"name": m.name, "initials": initials_for(m.name)}
        for m in Manager.objects.filter(is_active_session=True)
    ]


def compute_location_stats(location):
    tasks = Task.objects.filter(heading__location=location, task_type__in=["normal", "regulatory_doc"])
    total = tasks.count()
    done = sum(1 for t in tasks if t.status == "done")
    colors = [task_color(t) for t in tasks]
    location.percent_complete = round((done / total) * 100) if total else 0
    location.overdue_count = colors.count("red")
    location.at_risk_count = colors.count("yellow")
    location.status_color = worst_color(colors) if colors else "green"
    return location

def urgency_score(location):
    # already computed by compute_location_stats(): overdue_count, at_risk_count
    score = (location.overdue_count * 3) + (location.at_risk_count * 1)

    upcoming = (
        Task.objects.filter(heading__location=location, task_type__in=["normal", "regulatory_doc"])
        .exclude(status="done")
    )
    soonest_days = None
    for t in upcoming:
        if task_color(t) == "red":
            continue  # already counted via overdue_count above
        days_left = (t.end_date - date.today()).days
        if soonest_days is None or days_left < soonest_days:
            soonest_days = days_left

    if soonest_days is not None and soonest_days <= 14:
        score += max(0, 14 - soonest_days)

    return score

def can_access_location(manager, location):
    if manager.is_admin:
        return True
    if manager.department_id == location.department_id:
        return True
    if location.shared_with_managers.filter(id=manager.id).exists():
        return True
    return False

# ---------------------------------------------------------------
# Item 2 — real views, querying the database
# ---------------------------------------------------------------

def homepage(request):
    manager = request.current_manager
    if manager.is_admin:
        visible = Location.objects.filter(is_archived=False)
    else:
        visible = Location.objects.filter(is_archived=False).filter(
            models.Q(department=manager.department) | models.Q(shared_with_managers=manager)
        ).distinct()

    locations = [compute_location_stats(loc) for loc in visible]
    locations.sort(key=lambda l: (-l.overdue_count, -l.at_risk_count, l.name))
    return render(request, "tracker/homepage.html", {
        "locations": locations,
        "online_managers": get_online_managers(),
    })

def completed_projects(request):
    manager = request.current_manager
    if manager.is_admin:
        visible = Location.objects.filter(is_archived=True)
    else:
        visible = Location.objects.filter(is_archived=True).filter(
            models.Q(department=manager.department) | models.Q(shared_with_managers=manager)
        ).distinct()

    locations = [compute_location_stats(loc) for loc in visible]
    locations.sort(key=lambda l: l.archived_at, reverse=True)
    return render(request, "tracker/completed_projects.html", {
        "locations": locations,
        "online_managers": get_online_managers(),
    })


def archive_location(request, location_id):
    location = get_object_or_404(Location, id=location_id)
    if not can_access_location(request.current_manager, location):
        return render(request, "tracker/access_denied.html", status=403)
    if request.method == "POST":
        location.is_archived = True
        location.archived_at = timezone.now()
        location.save()
    return redirect("homepage")


def restore_location(request, location_id):
    location = get_object_or_404(Location, id=location_id)
    if not can_access_location(request.current_manager, location):
        return render(request, "tracker/access_denied.html", status=403)
    if request.method == "POST":
        location.is_archived = False
        location.archived_at = None
        location.save()
    return redirect("completed_projects")


def add_location(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if name:
            location = Location.objects.create(name=name, department=request.current_manager.department)
            # every location gets all 6 fixed scope headings automatically
            for heading_key, _ in ScopeHeading.HEADING_CHOICES:
                if heading_key == "custom":
                    continue
                ScopeHeading.objects.create(location=location, heading_name=heading_key)
        return redirect("homepage")
    return render(request, "tracker/add_location.html", {
        "online_managers": get_online_managers(),
    })


def location_detail(request, location_id):
    location = get_object_or_404(Location, id=location_id)
    if not can_access_location(request.current_manager, location):
        return render(request, "tracker/access_denied.html", status=403)
    compute_location_stats(location)

    all_headings = list(location.scope_headings.all())
    fixed = [h for h in all_headings if h.heading_name in HEADING_ORDER]
    custom = [h for h in all_headings if h.heading_name not in HEADING_ORDER]
    fixed.sort(key=lambda h: HEADING_ORDER.index(h.heading_name))
    custom.sort(key=lambda h: h.id)
    scope_headings = fixed + custom

    for h in scope_headings:
        tasks = Task.objects.filter(heading=h, task_type__in=["normal", "regulatory_doc"])
        total = tasks.count()
        done = sum(1 for t in tasks if t.status == "done")
        colors = [task_color(t) for t in tasks]
        h.name = h.custom_label if h.heading_name == "custom" else h.get_heading_name_display()
        h.slug = f"custom-{h.id}" if h.heading_name == "custom" else h.heading_name
        h.total_count = total
        h.done_count = done
        h.status_color = worst_color(colors) if colors else "green"

    return render(request, "tracker/location_detail.html", {
        "location": location,
        "scope_headings": scope_headings,
        "online_managers": get_online_managers(),
    })

def add_deliverable(request, location_id):
    location = get_object_or_404(Location, id=location_id)
    if not can_access_location(request.current_manager, location):
        return render(request, "tracker/access_denied.html", status=403)
    if request.method == "POST":
        name = request.POST.get("deliverable_name", "").strip()
        if name:
            ScopeHeading.objects.create(location=location, heading_name="custom", custom_label=name)
    return redirect("location_detail", location_id=location.id)

def task_list(request, location_id, heading_slug):
    location = get_object_or_404(Location, id=location_id)
    if not can_access_location(request.current_manager, location):
        return render(request, "tracker/access_denied.html", status=403)
    heading = get_heading(location, heading_slug)

    tasks = list(Task.objects.filter(heading=heading, task_type__in=["normal", "regulatory_doc"]).select_related("assignee"))
    for t in tasks:
        t.color = task_color(t)
        t.status_slug = t.status

    heading.name = heading.custom_label if heading.heading_name == "custom" else heading.get_heading_name_display()
    heading.slug = f"custom-{heading.id}" if heading.heading_name == "custom" else heading.heading_name

    return render(request, "tracker/task_list.html", {
        "location": location,
        "heading": heading,
        "tasks": tasks,
        "online_managers": get_online_managers(),
    })



def add_task(request, location_id, heading_slug):
    location = get_object_or_404(Location, id=location_id)
    if not can_access_location(request.current_manager, location):
        return render(request, "tracker/access_denied.html", status=403)
    heading = get_heading(location, heading_slug)

    if request.method == "POST":
        name = request.POST.get("task_name", "").strip()
        start_date = request.POST.get("start_date") or date.today()
        end_date = request.POST.get("end_date") or date.today()
        if name:
            task_type = "regulatory_doc" if heading.heading_name == "regulatory_documents" else "normal"
            task = Task.objects.create(
                heading=heading, name=name, task_type=task_type,
                start_date=start_date, end_date=end_date,
                assignee=request.current_manager,
            )
            return redirect("task_detail", task_id=task.id)

    heading.name = heading.custom_label if heading.heading_name == "custom" else heading.get_heading_name_display()
    heading.slug = f"custom-{heading.id}" if heading.heading_name == "custom" else heading.heading_name
    return render(request, "tracker/add_task.html", {
        "location": location, "heading": heading,
        "online_managers": get_online_managers(),
    })


# ---------------------------------------------------------------
# Item 4 — task detail: actually save edits, remarks, audit log
# ---------------------------------------------------------------

def task_detail(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    if not can_access_location(request.current_manager, task.heading.location):
        return render(request, "tracker/access_denied.html", status=403)
    assignees = Manager.objects.all()

    task.heading.name = task.heading.custom_label if task.heading.heading_name == "custom" else task.heading.get_heading_name_display()
    task.heading.slug = f"custom-{task.heading.id}" if task.heading.heading_name == "custom" else task.heading.heading_name

    if request.method == "POST":
        changes = []

        new_assignee_id = request.POST.get("assignee_id")
        if new_assignee_id and str(task.assignee_id) != new_assignee_id:
            old_name = task.assignee.name if task.assignee else "—"
            new_manager = Manager.objects.get(id=new_assignee_id)
            changes.append(("assignee", old_name, new_manager.name))
            task.assignee = new_manager

        if request.POST.get("finish_task") == "1":
            changes.append(("status", task.get_status_display(), "Done"))
            task.status = "done"
            task.actual_end_date = date.today()
        else:
            new_status = request.POST.get("status")
            if new_status and new_status != task.status:
                changes.append(("status", task.get_status_display(),
                                dict(Task.STATUS_CHOICES).get(new_status, new_status)))
                task.status = new_status

        if task.task_type == "regulatory_doc":
            new_doc_status = request.POST.get("doc_status")
            if new_doc_status and new_doc_status != task.doc_status:
                changes.append(("doc_status", task.doc_status, new_doc_status))
                task.doc_status = new_doc_status

        new_funds_type = request.POST.get("funds_type")
        if new_funds_type and new_funds_type != task.funds_type:
            changes.append(("funds_type", task.funds_type, new_funds_type))
            task.funds_type = new_funds_type
        if new_funds_type == "amount":
            new_amount = request.POST.get("funds_amount") or None
            if str(task.funds_amount) != str(new_amount):
                changes.append(("funds_amount", str(task.funds_amount), str(new_amount)))
                task.funds_amount = new_amount

        task.save()

        changed_by = request.current_manager
        for field, old, new in changes:
            AuditLogEntry.objects.create(
                task=task, field_changed=field,
                old_value=old or "", new_value=new or "", changed_by=changed_by,
            )

        remark_text = request.POST.get("new_remark", "").strip()
        if remark_text:
            Remark.objects.create(task=task, author=changed_by, text=remark_text)

        return redirect("task_detail", task_id=task.id)

    task.color = task_color(task)
    return render(request, "tracker/task_detail.html", {
        "task": task,
        "assignees": assignees,
        "audit_log": task.audit_log.order_by("-changed_at"),
        "online_managers": get_online_managers(),
    })


def add_action_point(request, task_id):
    parent = get_object_or_404(Task, id=task_id)
    if not can_access_location(request.current_manager, parent.heading.location):
        return render(request, "tracker/access_denied.html", status=403)
    Task.objects.create(
        heading=parent.heading, parent_task=parent, task_type="action_point",
        name="New action point", start_date=date.today(), end_date=date.today(),
        assignee=request.current_manager,
    )
    return redirect("task_detail", task_id=parent.id)


# ---------------------------------------------------------------
# Login / logout — still stubs, item 1 not built yet
# ---------------------------------------------------------------

def login_page(request):
    error = None
    if request.method == "POST":
        staff_id = request.POST.get("staff_id", "").strip()
        password = request.POST.get("password", "")
        manager = Manager.objects.filter(staff_id=staff_id).first()

        if manager and check_password(password, manager.password_hash):
            request.session["manager_id"] = manager.id
            now = timezone.now()
            manager.last_login_at = now
            manager.last_activity_at = now
            manager.is_active_session = True
            manager.save()
            return redirect("homepage")
        else:
            # deliberately generic — doesn't reveal whether the staff ID exists
            error = "Incorrect staff ID or password."

    return render(request, "tracker/login.html", {"error": error})


def logout_view(request):
    manager_id = request.session.get("manager_id")
    if manager_id:
        Manager.objects.filter(id=manager_id).update(is_active_session=False)
    request.session.flush()
    return redirect("login")


# ---------------------------------------------------------------
# Archive — unchanged placeholder, items 6/7 not built yet
# ---------------------------------------------------------------

def archive(request):
    snapshots = DailySnapshot.objects.order_by("-snapshot_date")
    return render(request, "tracker/archive.html", {
        "snapshots": snapshots,
        "online_managers": get_online_managers(),
    })


def archive_detail(request, snapshot_id):
    snapshot = get_object_or_404(DailySnapshot, id=snapshot_id)
    locations = snapshot.data.get("locations", [])
    locations.sort(key=lambda l: (-l["overdue_count"], -l["at_risk_count"], l["name"]))
    return render(request, "tracker/homepage.html", {
        "locations": locations,
        "online_managers": get_online_managers(),
        "is_archived_view": True,
        "snapshot_date": snapshot.snapshot_date.strftime("%b ") + str(snapshot.snapshot_date.day) + snapshot.snapshot_date.strftime(", %Y"),
    })


# ---------------------------------------------------------------
# Item 8 — who's online endpoint
# ---------------------------------------------------------------

def online_status(request):
    return JsonResponse({"managers": get_online_managers()})


ADMIN_SESSION_KEY = "admin_reset_authenticated_until"
ADMIN_ATTEMPTS_KEY = "admin_reset_attempts"
ADMIN_LOCKOUT_KEY = "admin_reset_lockout_until"


def admin_reset(request):
    now = timezone.now()

    lockout_until = request.session.get(ADMIN_LOCKOUT_KEY)
    locked_out = lockout_until and now.timestamp() < lockout_until

    authenticated_until = request.session.get(ADMIN_SESSION_KEY)
    is_authenticated = authenticated_until and now.timestamp() < authenticated_until

    error = None
    success = None

    if request.method == "POST":
        if not is_authenticated:
            # ---- stage 1: checking the admin password ----
            if locked_out:
                error = "Too many attempts. Please wait before trying again."
            else:
                entered = request.POST.get("admin_password", "")
                if check_password(entered, settings.ADMIN_PASSWORD_HASH):
                    request.session[ADMIN_SESSION_KEY] = (now + timedelta(minutes=5)).timestamp()
                    request.session[ADMIN_ATTEMPTS_KEY] = 0
                    is_authenticated = True
                else:
                    attempts = request.session.get(ADMIN_ATTEMPTS_KEY, 0) + 1
                    request.session[ADMIN_ATTEMPTS_KEY] = attempts
                    if attempts >= 4:
                        request.session[ADMIN_LOCKOUT_KEY] = (now + timedelta(seconds=30)).timestamp()
                        request.session[ADMIN_ATTEMPTS_KEY] = 0
                        error = "Too many attempts. Please wait 30 seconds before trying again."
                    else:
                        error = "Incorrect password."
        else:
            # ---- stage 2: performing the actual reset ----
            staff_id = request.POST.get("staff_id", "").strip()
            new_password = request.POST.get("new_password", "")
            confirm_password = request.POST.get("confirm_password", "")

            manager = Manager.objects.filter(staff_id=staff_id).first()
            if not manager:
                error = "No manager found with that staff ID."
            elif len(new_password) < 8:
                error = "New password must be at least 8 characters."
            elif new_password != confirm_password:
                error = "Passwords do not match."
            else:
                manager.password_hash = make_password(new_password)
                manager.is_active_session = False  # force logout of their current session
                manager.save()
                PasswordResetLog.objects.create(manager=manager)
                success = f"Password updated for {manager.name} ({manager.staff_id})."

    if not is_authenticated:
        return render(request, "tracker/admin_reset_gate.html", {"error": error})

    recent_resets = PasswordResetLog.objects.select_related("manager").order_by("-reset_at")[:10]
    return render(request, "tracker/admin_reset_panel.html", {
        "error": error,
        "success": success,
        "recent_resets": recent_resets,
    })

@csrf_exempt
def admin_reset_logout(request):
    request.session.pop(ADMIN_SESSION_KEY, None)
    if request.POST.get("manual") == "1":
        return redirect("admin_reset")
    return HttpResponse(status=204)

def build_homepage_report_data():
    all_locations = list(Location.objects.all())
    for loc in all_locations:
        compute_location_stats(loc)

    completed = [l for l in all_locations if l.is_archived]
    active = [l for l in all_locations if not l.is_archived]

    total_overdue = sum(l.overdue_count for l in active)
    total_at_risk = sum(l.at_risk_count for l in active)
    total_on_time = sum(
        1 for l in active
        for t in Task.objects.filter(heading__location=l, task_type__in=["normal", "regulatory_doc"])
        if task_color(t) == "green"
    )

    concerns = [l for l in active if l.overdue_count > 0 or l.at_risk_count > 0]
    concerns.sort(key=lambda l: (-l.overdue_count, -l.at_risk_count))

    focus = sorted(active, key=urgency_score, reverse=True)
    focus = [l for l in focus if urgency_score(l) > 0][:5]

    return {
        "generated_at": timezone.now(),
        "completed": completed,
        "active": active,
        "total_overdue": total_overdue,
        "total_at_risk": total_at_risk,
        "total_on_time": total_on_time,
        "concerns": concerns,
        "focus": focus,
    }


def build_location_report_data(location):
    # Same deliverable ordering used on the location dashboard: fixed
    # headings first (in HEADING_ORDER), then custom deliverables by id.
    all_headings = list(location.scope_headings.all())
    fixed = [h for h in all_headings if h.heading_name in HEADING_ORDER]
    custom = [h for h in all_headings if h.heading_name not in HEADING_ORDER]
    fixed.sort(key=lambda h: HEADING_ORDER.index(h.heading_name))
    custom.sort(key=lambda h: h.id)
    headings = fixed + custom

    done_by_deliverable = []
    todo = []
    late = []

    for h in headings:
        label = h.custom_label if h.heading_name == "custom" else h.get_heading_name_display()
        h_tasks = list(
            Task.objects.filter(heading=h, task_type__in=["normal", "regulatory_doc"]).select_related("assignee")
        )
        for t in h_tasks:
            t.color = task_color(t)

        h_done = [t for t in h_tasks if t.status == "done"]

        if h_done:
            done_by_deliverable.append({
                "label": label,
                # Whole deliverable is finished — no need to itemize it.
                "fully_done": len(h_done) == len(h_tasks),
                "tasks": h_done,
            })

        for t in h_tasks:
            if t.status == "done":
                continue
            if t.color == "red":
                late.append(t)
            else:
                todo.append(t)

    done_count = sum(len(group["tasks"]) for group in done_by_deliverable)

    return {
        "generated_at": timezone.now(),
        "location": location,
        "done_by_deliverable": done_by_deliverable,
        "done_count": done_count,
        "todo": todo,
        "late": late,
        "overdue_count": len(late),
        "at_risk_count": sum(1 for t in todo if t.color == "yellow"),
        "on_time_count": sum(1 for t in todo if t.color == "green"),
    }

def _add_heading(doc, text, level=1):
    doc.add_heading(text, level=level)

def _add_bullet(doc, text, color_hex=None):
    p = doc.add_paragraph(style="List Bullet")
    run = p.add_run(text)
    if color_hex:
        run.font.color.rgb = RGBColor(*hex_to_rgb(color_hex))
    return p

def _status_hex(theme, status):
    # Holds the colors resolved live from styles.css, so a
    # dashboard color change is picked up here automatically.
    return theme["hex"].get(status)

def generate_homepage_docx(data, theme):
    doc = Document()
    _add_heading(doc, "Project Overview Report", level=0)
    doc.add_paragraph(f"Generated {data['generated_at'].strftime('%Y-%m-%d %H:%M')}")

    _add_heading(doc, "Completed Projects")
    if data["completed"]:
        for l in data["completed"]:
            _add_bullet(doc, l.name, _status_hex(theme, "green"))
    else:
        doc.add_paragraph("None yet.")

    _add_heading(doc, "Active Projects")
    for l in data["active"]:
        _add_bullet(doc, f"{l.name} — {l.percent_complete}% complete", _status_hex(theme, l.status_color))

    _add_heading(doc, "Task Overview")
    doc.add_paragraph(f"Overdue: {data['total_overdue']}    At risk: {data['total_at_risk']}    On time: {data['total_on_time']}")

    _add_heading(doc, "Projects of Concern")
    if data["concerns"]:
        for l in data["concerns"]:
            _add_bullet(doc, f"{l.name} — {l.overdue_count} overdue, {l.at_risk_count} at risk", _status_hex(theme, l.status_color))
    else:
        doc.add_paragraph("No projects currently of concern.")

    _add_heading(doc, "Suggested Focus")
    if data["focus"]:
        for l in data["focus"]:
            _add_bullet(doc, l.name, _status_hex(theme, l.status_color))
    else:
        doc.add_paragraph("Nothing urgent right now.")

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def generate_location_docx(data, theme):
    doc = Document()
    location = data["location"]
    _add_heading(doc, f"{location.name} — Site Report", level=0)
    doc.add_paragraph(f"Generated {data['generated_at'].strftime('%Y-%m-%d %H:%M')}")

    _add_heading(doc, "Task Overview")
    doc.add_paragraph(f"Overdue: {data['overdue_count']}    At risk: {data['at_risk_count']}    On time: {data['on_time_count']}")

    _add_heading(doc, "Done")
    if data["done_by_deliverable"]:
        for group in data["done_by_deliverable"]:
            if group["fully_done"]:
                # Whole deliverable is complete — just state the label.
                _add_bullet(doc, f"{group['label']} — complete", _status_hex(theme, "green"))
            else:
                label_p = doc.add_paragraph()
                label_p.add_run(group["label"]).bold = True
                for t in group["tasks"]:
                    _add_bullet(doc, t.name, _status_hex(theme, t.color))
    else:
        doc.add_paragraph("Nothing completed yet.")

    _add_heading(doc, "To Do")
    for t in data["todo"]:
        _add_bullet(doc, f"{t.name} (due {t.end_date})", _status_hex(theme, t.color))
    if not data["todo"]:
        doc.add_paragraph("Nothing outstanding.")

    _add_heading(doc, "Running Late")
    for t in data["late"]:
        _add_bullet(doc, f"{t.name} (was due {t.end_date})", _status_hex(theme, "red"))
    if not data["late"]:
        doc.add_paragraph("Nothing overdue.")

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

def homepage_report(request):
    data = build_homepage_report_data()
    theme = get_report_theme()
    fmt = request.GET.get("format", "pdf")

    if fmt == "word":
        buffer = generate_homepage_docx(data, theme)
        response = HttpResponse(buffer.read(), content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        response["Content-Disposition"] = 'attachment; filename="project_overview_report.docx"'
        return response

    html_string = render_to_string("tracker/reports/homepage_report.html", {"data": data, "theme": theme})
    pdf_bytes = HTML(string=html_string).write_pdf()
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="project_overview_report.pdf"'
    return response


def location_report(request, location_id):
    location = get_object_or_404(Location, id=location_id)
    if not can_access_location(request.current_manager, location):
        return render(request, "tracker/access_denied.html", status=403)
    data = build_location_report_data(location)
    theme = get_report_theme()
    fmt = request.GET.get("format", "pdf")

    if fmt == "word":
        buffer = generate_location_docx(data, theme)
        response = HttpResponse(buffer.read(), content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        response["Content-Disposition"] = f'attachment; filename="{location.name}_report.docx"'
        return response

    html_string = render_to_string("tracker/reports/location_report.html", {"data": data, "theme": theme})
    pdf_bytes = HTML(string=html_string).write_pdf()
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{location.name}_report.pdf"'
    return response

def manage_access_hub(request):
    if not request.current_manager.is_admin:
        return render(request, "tracker/access_denied.html", status=403)
    locations = Location.objects.filter(is_archived=False)
    return render(request, "tracker/manage_access_hub.html", {
        "locations": locations,
        "online_managers": get_online_managers(),
    })


def manage_access(request, location_id):
    if not request.current_manager.is_admin:
        return render(request, "tracker/access_denied.html", status=403)

    location = get_object_or_404(Location, id=location_id)

    if request.method == "POST":
        selected_ids = request.POST.getlist("shared_managers")
        location.shared_with_managers.set(selected_ids)
        return redirect("manage_access", location_id=location.id)

    all_managers = Manager.objects.exclude(department=location.department)
    shared_ids = set(location.shared_with_managers.values_list("id", flat=True))
    return render(request, "tracker/manage_access.html", {
        "location": location,
        "all_managers": all_managers,
        "shared_ids": shared_ids,
        "online_managers": get_online_managers(),
    })

def remove_deliverable(request, location_id, heading_id):
    location = get_object_or_404(Location, id=location_id)
    heading = get_object_or_404(ScopeHeading, id=heading_id, location=location, heading_name="custom")
    if request.method == "POST":
        heading.delete()
    return redirect("location_detail", location_id=location.id)