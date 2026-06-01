from django.conf import settings

from equipment.services.agent_install import agent_install_enabled, should_show_agent_install_prompt


def agent_install_prompt(request):
    if not should_show_agent_install_prompt(request):
        return {'jp_show_agent_install': False}

    from django.urls import reverse

    return {
        'jp_show_agent_install': True,
        'jp_agent_download_url': reverse('equipment:agent_download_installer'),
        'jp_agent_enabled': agent_install_enabled(),
    }
