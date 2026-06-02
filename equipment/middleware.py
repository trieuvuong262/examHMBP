from django.shortcuts import redirect
from django.urls import reverse

from equipment.services.agent_install import is_agent_install_required


class AgentInstallGateMiddleware:
    """Chặn portal cho đến khi user Windows cài agent và có trong quản lý thiết bị."""

    _ALLOWED_PREFIXES = (
        '/static/',
        '/media/',
        '/accounts/logout/',
        '/change-password',
        '/thiet-bi/agent/yeu-cau-cai',
        '/thiet-bi/agent/xac-nhan-chung/',
        '/thiet-bi/agent/tai-cai-dat',
        '/thiet-bi/agent/exe/',
        '/thiet-bi/agent/cai-portal-app/',
        '/thiet-bi/agent/hoan-tat/',
        '/thiet-bi/agent/trang-thai/',
        '/thiet-bi/agent/ping/',
        '/thiet-bi/api/agent-report/',
        '/thiet-bi/api/agent-poll/',
    )

    def __init__(self, get_response):
        self.get_response = get_response
        self._gate_url = reverse('equipment:agent_install_gate')

    def __call__(self, request):
        if is_agent_install_required(request):
            path = request.path
            if not self._is_gate_path(path) and not self._path_allowed(path):
                return redirect('equipment:agent_install_gate')
        return self.get_response(request)

    def _is_gate_path(self, path: str) -> bool:
        return path.rstrip('/') == self._gate_url.rstrip('/')

    def _path_allowed(self, path: str) -> bool:
        if path.startswith('/admin-panel/'):
            return True
        return any(path.startswith(prefix) for prefix in self._ALLOWED_PREFIXES)
