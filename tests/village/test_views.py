"""Tests for village views."""
import datetime

from django.core import mail
from django.core.urlresolvers import reverse
from django.utils.timezone import utc

import pytest

from portfoliyo.village import views

from tests import utils
from tests.users import factories as uf
from tests.village.factories import PostFactory




class TestDashboard(object):
    def test_dashboard(self, client):
        """A picklist of students."""
        rel = uf.RelationshipFactory(to_profile__name="Student One")
        uf.RelationshipFactory(
            from_profile=rel.elder, to_profile__name="Student Two")
        response = client.get(
            reverse('dashboard'), user=rel.elder.user, status=200)

        response.mustcontain("Please select a student")
        response.mustcontain("Student One")
        response.mustcontain("Student Two")



class TestAddStudent(object):
    """Tests for add_student view."""
    def test_add_student(self, client):
        """User can add a student and invite some elders."""
        teacher = uf.ProfileFactory.create(school_staff=True)
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
            reverse('village', kwargs={'student_id': student.id}))


    def test_validation_error(self, client):
        """Name of student must be provided."""
        teacher = uf.ProfileFactory.create(school_staff=True)
        form = client.get(
            reverse('add_student'), user=teacher.user).forms['add-student-form']
        form['elders-0-contact'] = "(123)456-7890"
        form['elders-0-relationship'] = "Father"
        form['elders-0-school_staff'] = False
        response = form.submit(status=200)

        response.mustcontain("field is required")


    def test_requires_school_staff(self, client):
        """Adding a student requires ``school_staff`` attribute."""
        someone = uf.ProfileFactory.create(school_staff=False)
        response = client.get(
            reverse('add_student'), user=someone.user, status=302).follow()

        response.mustcontain("account doesn't have access"), response.html


    def test_anonymous_user_doesnt_blow_up(self, client):
        """Anonymous user on school-staff-required redirects gracefully."""
        response = client.get(reverse('add_student'), status=302).follow()

        assert not "account doesn't have access" in response.content



class TestInviteElders(object):
    """Tests for invite_elders view."""
    def url(self, student=None):
        if student is None:
            student = uf.ProfileFactory.create()
        return reverse('invite_elders', kwargs=dict(student_id=student.id))


    def test_invite_elders(self, client):
        """User can invite some elders."""
        rel = uf.RelationshipFactory.create(
            from_profile__school_staff=True)
        response = client.get(self.url(rel.student), user=rel.elder.user)
        form = response.forms['invite-elders-form']
        form['elders-0-contact'] = "dad@example.com"
        form['elders-0-relationship'] = "Father"
        form['elders-0-school_staff'] = False
        response = form.submit(status=302)

        assert response['Location'] == utils.location(
            reverse('village', kwargs={'student_id': rel.student.id}))

        # invite email is sent to new elder
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [u'dad@example.com']


    def test_validation_error(self, client):
        """If one elder field is filled out, other must be too."""
        rel = uf.RelationshipFactory.create(
            from_profile__school_staff=True)
        response = client.get(self.url(rel.student), user=rel.elder.user)
        form = response.forms['invite-elders-form']
        form['elders-0-contact'] = "(123)456-7890"
        form['elders-0-relationship'] = ""
        form['elders-0-school_staff'] = False
        response = form.submit(status=200)

        response.mustcontain("field is required")


    def test_requires_school_staff(self, client):
        """Inviting elders requires ``school_staff`` attribute."""
        rel = uf.RelationshipFactory.create(
            from_profile__school_staff=False)
        response = client.get(
            self.url(rel.student), user=rel.elder.user, status=302).follow()

        response.mustcontain("account doesn't have access"), response.html


    def test_requires_relationship(self, client):
        """Only an elder of that student can invite more."""
        elder = uf.ProfileFactory.create(school_staff=True)
        student = uf.ProfileFactory.create()

        client.get(self.url(student), user=elder.user, status=404)



class TestVillage(object):
    """Tests for village chat view."""
    def url(self, student=None):
        if student is None:
            student = uf.ProfileFactory.create()
        return reverse('village', kwargs=dict(student_id=student.id))


    @pytest.mark.parametrize('link_target', ['add_student', 'invite_elders'])
    def test_button_only_if_staff(self, client, link_target):
        """Button with given link target is only present for school staff."""
        parent_rel = uf.RelationshipFactory.create(
            from_profile__school_staff=False)
        teacher_rel = uf.RelationshipFactory.create(
            from_profile__school_staff=True, to_profile=parent_rel.student)
        url = self.url(parent_rel.student)
        parent_response = client.get(url, user=parent_rel.elder.user)
        teacher_response = client.get(url, user=teacher_rel.elder.user)
        reverse_kwargs = {}
        if link_target == 'invite_elders':
            reverse_kwargs = {'student_id': parent_rel.student.id}
        target_url = reverse(link_target, kwargs=reverse_kwargs)
        parent_links = parent_response.html.findAll('a', href=target_url)
        teacher_links = teacher_response.html.findAll('a', href=target_url)

        assert len(teacher_links) == 1
        assert len(parent_links) == 0


    def test_requires_relationship(self, client):
        """Only an elder of that student can view village."""
        elder = uf.ProfileFactory.create(school_staff=True)
        student = uf.ProfileFactory.create()

        client.get(self.url(student), user=elder.user, status=404)



class TestJsonPosts(object):
    """Tests for json_posts view."""
    def url(self, student=None):
        if student is None:
            student = uf.ProfileFactory.create()
        return reverse('json_posts', kwargs=dict(student_id=student.id))


    def test_requires_relationship(self, client):
        """Only an elder of that student can get posts."""
        elder = uf.ProfileFactory.create(school_staff=True)
        student = uf.ProfileFactory.create()

        client.get(self.url(student), user=elder.user, status=404)


    def test_create_post(self, no_csrf_client):
        """Creates a post and returns its JSON representation."""
        rel = uf.RelationshipFactory.create()

        response = no_csrf_client.post(
            self.url(rel.student), {'text': 'foo'}, user=rel.elder.user)

        assert response.json['success']
        posts = response.json['posts']
        assert len(posts) == 1
        post = posts[0]
        assert post['text'] == 'foo'
        assert post['author_id'] == rel.elder.id
        assert post['student_id'] == rel.student.id


    def test_create_post_with_sequence_id(self, no_csrf_client):
        """Can include a sequence_id with post, will get it back."""
        rel = uf.RelationshipFactory.create()

        response = no_csrf_client.post(
            self.url(rel.student),
            {'text': 'foo', 'author_sequence_id': '5'},
            user=rel.elder.user,
            )

        assert response.json['posts'][0]['author_sequence_id'] == '5'


    def test_length_limit(self, no_csrf_client):
        """Error if post is too long."""
        rel = uf.RelationshipFactory.create(
            from_profile__name='Fred')

        response = no_csrf_client.post(
            self.url(rel.student),
            {'text': 'f' * 160},
            user=rel.elder.user,
            status=400,
            )

        # length limit is 160 - len('Fred: ')
        assert response.json == {
            'success': False,
            'error': "Posts are limited to 154 characters."
            }


    def test_get_posts(self, client):
        """Get backlog posts in chronological order."""
        rel = uf.RelationshipFactory.create(
            from_profile__name='Fred')

        PostFactory(
            timestamp=datetime.datetime(2012, 9, 17, 3, 8, tzinfo=utc),
            author=rel.elder,
            student=rel.student,
            html_text='post1',
            )
        PostFactory(
            timestamp=datetime.datetime(2012, 9, 17, 3, 5, tzinfo=utc),
            author=rel.elder,
            student=rel.student,
            html_text='post2',
            )
        # not in same village, shouldn't be returned
        PostFactory()

        response = client.get(self.url(rel.student), user=rel.elder.user)

        posts = response.json['posts']
        assert [p['text'] for p in posts] == ['post2', 'post1']


    def test_backlog_limit(self, client, monkeypatch):
        """There's a limit on number of posts returned."""
        rel = uf.RelationshipFactory.create(
            from_profile__name='Fred')

        PostFactory(
            timestamp=datetime.datetime(2012, 9, 17, 3, 8, tzinfo=utc),
            author=rel.elder,
            student=rel.student,
            html_text='post1',
            )
        PostFactory(
            timestamp=datetime.datetime(2012, 9, 17, 3, 5, tzinfo=utc),
            author=rel.elder,
            student=rel.student,
            html_text='post2',
            )

        monkeypatch.setattr(views, "BACKLOG_POSTS", 1)
        response = client.get(self.url(rel.student), user=rel.elder.user)

        posts = response.json['posts']
        assert [p['text'] for p in posts] == ['post1']
