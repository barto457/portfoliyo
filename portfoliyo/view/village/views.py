"""
Student/elder (village) views.

"""
import json
import os

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest, Http404
from django.shortcuts import redirect, get_object_or_404
from django.template.response import TemplateResponse

from portfoliyo import model, pdf
from portfoliyo.view import home
from ..decorators import school_staff_required
from ..ajax import ajax
from . import forms


# number of posts to show in backlog
BACKLOG_POSTS = 100


@login_required
@ajax('village/_dashboard_content.html')
def dashboard(request):
    """Dashboard view for users with multiple students."""
    return TemplateResponse(
        request,
        'village/dashboard.html',
        {'elders_formset': forms.InviteEldersFormSet(prefix='elders')},
        )



@school_staff_required
@ajax('village/_add_student_content.html')
def add_student(request):
    """Add a student and elders."""
    if request.method == 'POST':
        form = forms.AddStudentAndInviteEldersForm(request.POST)
        if form.is_valid():
            student, _ = form.save(request, added_by=request.user.profile)
            return redirect('village', student_id=student.id)
    else:
        form = forms.AddStudentAndInviteEldersForm()

    return TemplateResponse(
        request,
        'village/add_student.html',
        {
            'form': form,
            'elders_formset': form.elders_formset,
            },
        )


def get_relationship_or_404(student_id, profile):
    """Get relationship between student_id and profile, or 404."""
    try:
        return model.Relationship.objects.select_related().get(
            from_profile=profile,
            to_profile_id=student_id,
            kind=model.Relationship.KIND.elder,
            )
    except model.Relationship.DoesNotExist:
        raise Http404



@school_staff_required
@ajax('village/_invite_elders_content.html')
def invite_elders(request, student_id):
    """Invite new elder(s) to a student's village."""
    rel = get_relationship_or_404(student_id, request.user.profile)

    if request.method == 'POST':
        formset = forms.InviteEldersFormSet(request.POST, prefix='elders')
        if formset.is_valid():
            formset.save(request, rel)
            return redirect('village', student_id=rel.student.id)
    else:
        formset = forms.InviteEldersFormSet(prefix='elders')

    return TemplateResponse(
        request,
        'village/invite_elders.html',
        {'elders_formset': formset, 'student': rel.student},
        )



@login_required
@ajax('village/_village_content.html')
def village(request, student_id):
    """The main chat view for a student/village."""
    rel = get_relationship_or_404(student_id, request.user.profile)

    if request.method == 'POST':
        if not rel.elder.school_staff:
            return redirect(request.path)
        if 'remove' in request.POST:
            rel.student.deleted = True
            rel.student.save()
            if not request.is_ajax():
                return redirect(home.redirect_home(request.user))
            data = {'success': True}
        else:
            form = forms.EditStudentForm(request.POST)
            if form.is_valid():
                form.save(rel.student)
                data = {'success': True, 'name': rel.student.name}
            else:
                for error in form.errors['name']:
                    messages.error(request, error)
                data = {'success': False, 'name': rel.student.name}
            if not request.is_ajax():
                return redirect(request.path)
        return HttpResponse(json.dumps(data), content_type='application/json')

    return TemplateResponse(
        request,
        'village/village.html',
        {
            'student': rel.student,
            'relationship': rel,
            'post_char_limit': model.post_char_limit(rel),
            'elders_formset': forms.InviteEldersFormSet(prefix='elders'),
            },
        )



@login_required
def json_posts(request, student_id):
    """Get backlog of up to 100 latest posts, or POST a post."""
    rel = get_relationship_or_404(student_id, request.user.profile)

    if request.method == 'POST' and 'text' in request.POST:
        text = request.POST['text']
        sequence_id = request.POST.get('author_sequence_id')
        limit = model.post_char_limit(rel)
        if len(text) > limit:
            return HttpResponseBadRequest(
                json.dumps(
                    {
                        'error': 'Posts are limited to %s characters.' % limit,
                        'success': False,
                        }
                    ),
                content_type='application/json',
                )
        post = model.Post.create(
            request.user.profile, rel.student, text, sequence_id)

        data = {
            'success': True,
            'posts': [model.post_dict(post, author_sequence_id=sequence_id)],
            }

        return HttpResponse(json.dumps(data), content_type='application/json')

    data = {
        'posts':
            [
            model.post_dict(post) for post in
            reversed(
                rel.student.posts_in_village.order_by(
                    '-timestamp')[:BACKLOG_POSTS]
                )
            ],
        }

    return HttpResponse(json.dumps(data), content_type='application/json')


@school_staff_required
@ajax('village/_edit_elder_content.html')
def edit_elder(request, student_id, elder_id):
    """Edit a village elder."""
    get_relationship_or_404(student_id, request.user.profile)
    elder = get_object_or_404(
        model.Profile.objects.select_related('user'), id=elder_id)
    # can't edit the profile of another school staff
    if elder.school_staff:
        raise Http404
    elder_rel = get_relationship_or_404(student_id, elder)

    if request.method == 'POST':
        form = forms.EditElderForm(request.POST, profile=elder)
        if form.is_valid():
            form.save()
            messages.success(request, u"Changes saved!")
            return redirect('village', student_id=student_id)
    else:
        form = forms.EditElderForm(profile=elder)

    return TemplateResponse(
        request,
        'village/edit_elder.html',
        {
            'form': form,
            'student': elder_rel.student,
            'elder': elder_rel.elder,
            'elders_formset': forms.InviteEldersFormSet(prefix='elders'),
            },
        )



@school_staff_required
def pdf_parent_instructions(request, lang):
    """Render a PDF for sending home with parents."""
    template_dir = os.path.dirname(os.path.abspath(pdf.__file__))
    template_path = os.path.join(
        template_dir,
        'parent-instructions-template-%s.pdf' % lang,
        )

    if not os.path.isfile(template_path):
        raise Http404

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = (
        'attachment; filename=instructions-%s.pdf' % lang)

    pdf.generate_instructions_pdf(
        template_path=template_path,
        stream=response,
        code=request.user.profile.code or '',
        phone=settings.PORTFOLIYO_SMS_DEFAULT_FROM,
        )

    return response