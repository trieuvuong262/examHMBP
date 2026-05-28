from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def user_guide(request):
    return render(request, 'guide/user_guide.html')
