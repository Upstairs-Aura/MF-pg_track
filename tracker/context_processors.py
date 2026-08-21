def current_manager(request):
    return {"current_manager": getattr(request, "current_manager", None)}