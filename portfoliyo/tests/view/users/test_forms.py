"""Tests for user-related forms."""
from portfoliyo.view.users import forms

from portfoliyo.tests import factories, utils


class TestRegistrationForm(object):
    """Tests for RegistrationForm."""
    base_data = {
        'name': 'Some Body',
        'email': 'some@example.com',
        'password': 'sekrit',
        'password_confirm': 'sekrit',
        'role': 'Some Role',
        }


    def test_unmatched_passwords(self):
        """Registration form not valid if passwords don't match."""
        data = self.base_data.copy()
        data['password'] = 'other-sekrit'
        form = forms.RegistrationForm(data)

        assert not form.is_valid()
        assert form.errors['__all__'] == [u"The passwords didn't match."]


    def test_dupe_email(self):
        """Registration form not valid if passwords don't match."""
        factories.UserFactory.create(email='some@example.com')
        form = forms.RegistrationForm(self.base_data.copy())

        assert not form.is_valid()
        assert form.errors['email'] == [
            u"This email address is already in use. "
            u"Please supply a different email address."
            ]


class TestEditProfileForm(object):
    def test_update_relationships(self):
        """
        Updating role updates matching relationship descriptions.

        If I have my role set in my profile as 'foo' and I change it to 'bar',
        any relationships where I am the elder and the relationship description
        is 'foo' will also be updated to 'bar'.

        """
        rel1 = factories.RelationshipFactory.create(
            description='foo', from_profile__role='foo')
        rel2 = factories.RelationshipFactory.create(
            description='bar', from_profile=rel1.elder)

        form = forms.EditProfileForm(
            {'name': 'New', 'role': 'new'}, profile=rel1.elder)
        assert form.is_valid()
        form.save()

        rel1 = utils.refresh(rel1)
        rel2 = utils.refresh(rel2)

        assert rel1.description == 'new'
        assert rel2.description == 'bar'