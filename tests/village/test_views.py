"""Tests for student-adding view."""
from django.core.urlresolvers import reverse

from tests import utils
from tests.users import factories


def test_add_student(client):
    """User can add a student and invite some elders."""
    teacher = factories.ProfileFactory.create(school_staff=True)
    form = client.get(
        reverse('add_student'), user=teacher.user).forms['add-student-form']
    form['name'] = "Some Student"
    form['elders-0-contact'] = "(123)456-7890"
    form['elders-0-relationship'] = "Father"
    form['elders-0-school_staff'] = False
    response = form.submit()

    student = teacher.students[0]

    assert response.status_code == 302, response.body
    assert response['Location'] == utils.location(
        reverse('chat', kwargs={'student_id': student.id}))
