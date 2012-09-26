"""Tests for Village SMS code."""
import mock

from portfoliyo import model
from portfoliyo.sms import hook

from portfoliyo.tests import factories, utils


def test_create_post():
    """Creates Post (and no reply) if one associated student."""
    phone = '+13216430987'
    profile = factories.ProfileFactory.create(phone=phone)
    rel = factories.RelationshipFactory.create(from_profile=profile)

    with mock.patch('portfoliyo.sms.hook.model.Post.create') as mock_create:
        reply = hook.receive_sms(phone, 'foo')

    assert reply is None
    mock_create.assert_called_once_with(
        profile, rel.student, 'foo', from_sms=True)



def test_activate_user():
    """Receiving SMS from inactive user activates and gives them more info."""
    phone = '+13216430987'
    profile = factories.ProfileFactory.create(
        user__is_active=False, phone=phone)
    rel = factories.RelationshipFactory.create(
        from_profile=profile, to_profile__name="Jimmy Doe")

    with mock.patch('portfoliyo.sms.hook.model.Post.create') as mock_create:
        reply = hook.receive_sms(phone, 'foo')

    assert utils.refresh(profile.user).is_active
    mock_create.assert_any_call(
        None, rel.student, hook.tag(phone, reply), to_sms=True, notify=False)
    assert reply == (
        "Thank you! You can text this number any time "
        "to talk with Jimmy Doe's teachers."
        )



def test_decline():
    """If an inactive user replies with 'stop', they are marked declined."""
    phone = '+13216430987'
    profile = factories.ProfileFactory.create(
        user__is_active=False, phone=phone)
    rel = factories.RelationshipFactory.create(from_profile=profile)

    with mock.patch('portfoliyo.sms.hook.model.Post.create') as mock_create:
        reply = hook.receive_sms(phone, 'stop')

    assert not utils.refresh(profile.user).is_active
    assert utils.refresh(profile).declined
    assert reply == (
        "No problem! Sorry to have bothered you."
        )
    mock_create.assert_any_call(profile, rel.student, "stop", from_sms=True)
    mock_create.assert_any_call(
        None, rel.student, hook.tag(phone, reply), to_sms=True, notify=False)



def test_active_user_decline():
    """If an active user replies with 'stop', they are marked declined."""
    phone = '+13216430987'
    profile = factories.ProfileFactory.create(
        user__is_active=True, phone=phone)
    rel = factories.RelationshipFactory.create(from_profile=profile)

    with mock.patch('portfoliyo.sms.hook.model.Post.create') as mock_create:
        reply = hook.receive_sms(phone, 'stop')

    assert not utils.refresh(profile.user).is_active
    assert utils.refresh(profile).declined
    assert reply == (
        "No problem! Sorry to have bothered you."
        )
    mock_create.assert_any_call(profile, rel.student, "stop", from_sms=True)
    mock_create.assert_any_call(
        None, rel.student, hook.tag(phone, reply), to_sms=True, notify=False)



def test_unknown_profile():
    """Reply if profile is unknown."""
    reply = hook.receive_sms('123', 'foo')

    assert reply == (
        "Bummer, we don't recognize your invite code! "
        "Please make sure it's typed exactly as it is on the paper, "
        "followed by a space and then your name."
        )


def test_multiple_students():
    """Reply if multiple associated students."""
    phone = '+13216430987'
    profile = factories.ProfileFactory.create(phone=phone)
    factories.RelationshipFactory.create(from_profile=profile)
    factories.RelationshipFactory.create(from_profile=profile)

    reply = hook.receive_sms(phone, 'foo')

    assert reply == (
        "You're part of more than one student's Portfoliyo Village; "
        "we're not yet able to route your texts. We'll fix that soon!"
        )


def test_no_students():
    """Reply if no associated students."""
    phone = '+13216430987'
    factories.ProfileFactory.create(phone=phone)

    reply = hook.receive_sms(phone, 'foo')

    assert reply == (
        "You're not part of any student's Portfoliyo Village, "
        "so we're not able to deliver your message. Sorry!"
        )


def test_code_signup():
    """Parent can create account by texting teacher code and their name."""
    phone = '+13216430987'
    teacher = factories.ProfileFactory.create(
        school_staff=True, name="Teacher Jane", code="ABCDEF")

    with mock.patch('portfoliyo.sms.hook.model.Post.create') as mock_create:
        reply = hook.receive_sms(phone, "abcdef John Doe")

    assert reply == (
        "Thanks! What is the name of your child in Teacher Jane's class?"
        )
    profile = model.Profile.objects.get(phone=phone)
    assert profile.name == "John Doe"
    assert profile.state == model.Profile.STATE.kidname
    assert profile.invited_by == teacher
    assert not mock_create.call_count


def test_code_signup_lacks_name():
    """If parent texts valid teacher code but omits name, they get help."""
    phone = '+13216430987'
    factories.ProfileFactory.create(
        school_staff=True, name="Teacher Jane", code="ABCDEF")

    with mock.patch('portfoliyo.sms.hook.model.Post.create') as mock_create:
        reply = hook.receive_sms(phone, "ABCDEF")

    assert reply == (
        "Please include your name after the code."
        )
    assert not mock_create.call_count


def test_code_signup_student_name():
    """Parent can continue code signup by providing student name."""
    phone = '+13216430987'
    teacher = factories.ProfileFactory.create(
        school_staff=True, name="Teacher Jane", code="ABCDEF")
    factories.ProfileFactory.create(
        name="John Doe",
        phone=phone,
        state=model.Profile.STATE.kidname,
        invited_by=teacher,
        )

    with mock.patch('portfoliyo.sms.hook.model.Post.create') as mock_create:
        reply = hook.receive_sms(phone, "Jimmy Doe")

    assert reply == (
        "Last question: what is your relationship to that child "
        "(mother, father, ...)?"
        )
    parent = model.Profile.objects.get(phone=phone)
    assert len(parent.students) == 1
    student = parent.students[0]
    assert student.name == u"Jimmy Doe"
    assert set(student.elders) == set([teacher, parent])
    assert parent.state == model.Profile.STATE.relationship
    # and the name is sent on to the village chat as a post
    mock_create.assert_any_call(parent, student, "Jimmy Doe", from_sms=True)
    # and the automated reply is also sent on to village chat
    mock_create.assert_any_call(
        None, student, hook.tag(phone, reply), to_sms=True, notify=False)


def test_code_signup_student_name_dupe_detection():
    """Don't create duplicate students in a teacher's class."""
    phone = '+13216430987'
    rel = factories.RelationshipFactory.create(
        from_profile__school_staff=True,
        to_profile__name="Jimmy Doe")
    factories.ProfileFactory.create(
        name="John Doe",
        phone=phone,
        state=model.Profile.STATE.kidname,
        invited_by=rel.elder,
        )

    with mock.patch('portfoliyo.sms.hook.model.Post.create'):
        reply = hook.receive_sms(phone, "Jimmy Doe")

    assert reply == (
        "Last question: what is your relationship to that child "
        "(mother, father, ...)?"
        )
    parent = model.Profile.objects.get(phone=phone)
    assert len(parent.students) == 1
    student = parent.students[0]
    assert student == rel.student


def test_code_signup_student_name_dupe_detection_excludes_deleted():
    """Go ahead and create a dupe student if the other is deleted."""
    phone = '+13216430987'
    rel = factories.RelationshipFactory.create(
        from_profile__school_staff=True,
        to_profile__name="Jimmy Doe",
        to_profile__deleted=True,
        )
    factories.ProfileFactory.create(
        name="John Doe",
        phone=phone,
        state=model.Profile.STATE.kidname,
        invited_by=rel.elder,
        )

    with mock.patch('portfoliyo.sms.hook.model.Post.create'):
        reply = hook.receive_sms(phone, "Jimmy Doe")

    assert reply == (
        "Last question: what is your relationship to that child "
        "(mother, father, ...)?"
        )
    parent = model.Profile.objects.get(phone=phone)
    assert len(parent.students) == 1
    student = parent.students[0]
    assert student != rel.student
    # teacher, parent, deleted student, new student
    assert model.Profile.objects.count() == 4


def test_code_signup_role():
    """Parent can finish code signup by providing their role."""
    phone = '+13216430987'
    teacher_rel = factories.RelationshipFactory.create(
        from_profile__school_staff=True,
        to_profile__name="Jimmy Doe")
    parent_rel = factories.RelationshipFactory.create(
        from_profile__name="John Doe",
        from_profile__role="",
        from_profile__phone=phone,
        from_profile__state=model.Profile.STATE.relationship,
        from_profile__invited_by=teacher_rel.elder,
        to_profile=teacher_rel.student,
        description="",
        )

    with mock.patch('portfoliyo.sms.hook.model.Post.create') as mock_create:
        reply = hook.receive_sms(phone, "father")

    assert reply == (
        "All done, thank you! You can text this number any time "
        "to talk with Jimmy Doe's teachers."
        )
    parent = model.Profile.objects.get(phone=phone)
    assert parent.role == "father"
    assert parent.state == model.Profile.STATE.done
    parent_rel = utils.refresh(parent_rel)
    assert parent_rel.description == "father"
    student = teacher_rel.student
    # and the role is sent on to the village chat as a post
    mock_create.assert_any_call(parent, student, "father", from_sms=True)
    # and the automated reply is also sent on to village chat
    mock_create.assert_any_call(
        None, student, hook.tag(phone, reply), to_sms=True, notify=False)


def test_get_teacher_and_name():
    """Gets teacher and parent name if text starts with teacher code."""
    teacher = factories.ProfileFactory.create(school_staff=True, code="ABCDEF")

    assert hook.get_teacher_and_name("abcdef foo") == (teacher, "foo")
    assert hook.get_teacher_and_name("ABCDEF") == (teacher, '')
    assert hook.get_teacher_and_name("ACDC bar") == (None, '')