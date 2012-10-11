"""
Student/elder forms.

"""
import floppyforms as forms

from portfoliyo import model, invites, formats
from ..forms import TemplateLabelModelMultipleChoiceField
from ..users.forms import EditProfileForm



class StudentCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    """A CheckboxSelectMultiple widget with a custom template."""
    template_name = 'village/student_checkbox_select.html'



class ElderCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    """A CheckboxSelectMultiple widget with a custom template."""
    template_name = 'village/elder_checkbox_select.html'



class GroupCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    """A CheckboxSelectMultiple widget with a custom template."""
    template_name = 'village/group_checkbox_select.html'



class EditElderForm(EditProfileForm):
    groups = TemplateLabelModelMultipleChoiceField(
        queryset=model.Group.objects.none(),
        widget=GroupCheckboxSelectMultiple,
        required=False,
        )
    students = TemplateLabelModelMultipleChoiceField(
        queryset=model.Profile.objects.none(),
        widget=StudentCheckboxSelectMultiple,
        required=False,
        )


    def __init__(self, *args, **kwargs):
        self.editor = kwargs.pop('editor')
        super(EditElderForm, self).__init__(*args, **kwargs)
        self.fields['groups'].queryset = model.Group.objects.filter(
            owner=self.editor)
        self.fields['students'].queryset = model.Profile.objects.filter(
            relationships_to__from_profile=self.editor, deleted=False)
        if self.instance.pk:
            self.fields['groups'].initial = [
                g.pk for g in self.instance.elder_in_groups.all()]
            self.fields['students'].initial = [
                s.pk for s in self.direct_students(self.instance)]


    def save(self, rel):
        """Save this elder in context of given village relationship."""
        self.instance.name = self.cleaned_data['name']
        old_profile_role = self.instance.role
        old_relationship_role = rel.description_or_role
        new_role = self.cleaned_data['role']
        if old_profile_role == old_relationship_role:
            self.instance.role = new_role
            self.instance.relationships_from.filter(
                description=old_profile_role).update(
                description='')
        else:
            rel.description = new_role
            rel.save()
        self.instance.save()

        self.instance.elder_in_groups = self.cleaned_data['groups']
        self.update_elder_students(self.instance, self.cleaned_data['students'])

        return self.instance


    def update_elder_students(self, elder, students):
        """Update elder to have exactly given direct (non-group) students."""
        current = set(self.direct_students(elder))
        target = set(students)
        remove = current.difference(target)
        add = target.difference(current)

        if remove:
            model.Relationship.objects.filter(
                from_profile=elder,
                to_profile__in=remove,
                ).delete()

        for student in add:
            model.Relationship.objects.get_or_create(
                to_profile=student,
                from_profile=elder,
                )


    def direct_students(self, elder):
        """
        Get all direct (non-group) students of an elder.

        Memoized by elder id.

        """
        if not hasattr(self, '_direct_students'):
            self._direct_students = {}
        if self._direct_students.get(elder.pk) is None:
            self._direct_students[elder.pk] = [
                r.student for r in
                model.Relationship.objects.filter(
                    from_profile=elder,
                    from_group=None,
                    to_profile__deleted=False,
                    ).select_related('to_profile')
                ]
        return self._direct_students[elder.pk]



class InviteElderForm(forms.Form):
    """A form for inviting an elder to a student village."""
    contact = forms.CharField(max_length=255)
    relationship = forms.CharField(max_length=200)
    school_staff = forms.BooleanField(required=False)


    def __init__(self, *args, **kwargs):
        """Accepts ``rel`` - relationship between inviting elder and student."""
        self.rel = kwargs.pop('rel')
        super(InviteElderForm, self).__init__(*args, **kwargs)


    def clean_contact(self):
        contact = self.cleaned_data["contact"]
        as_phone = formats.normalize_phone(contact)
        as_email = formats.normalize_email(contact)
        if as_phone:
            self.cleaned_data["phone"] = as_phone
            self.cleaned_data["email"] = None
        elif as_email:
            self.cleaned_data["email"] = as_email
            self.cleaned_data["phone"] = None
        else:
            raise forms.ValidationError(
                "Please supply a valid email address or US mobile number.")


    def save(self, request):
        """
        Save/return new elder profile and send invites, or return existing.

        Takes request (for details needed for email invite).

        """
        email = self.cleaned_data.get("email")
        phone = self.cleaned_data.get("phone")
        relationship = self.cleaned_data.get("relationship", u"")
        staff = self.cleaned_data.get("school_staff", False)

        # first check for an existing user match
        if email:
            dupe_query = {"user__email": email}
            active = False
        else:
            dupe_query = {"phone": phone}
            active = True
        try:
            profile = model.Profile.objects.get(**dupe_query)
        except model.Profile.DoesNotExist:
            profile = model.Profile.create_with_user(
                school=self.rel.student.school,
                email=email,
                phone=phone,
                role=relationship,
                is_active=active,
                )
            created = True
        else:
            created = False
            # update school_staff and role fields as needed
            if ((staff and not profile.school_staff) or
                    (relationship and not profile.role)):
                profile.school_staff = True
                if not profile.role:
                    profile.role = relationship
                profile.save()

        # create student's rel with invited elder (unless it already exists)
        new_rel, rel_created = model.Relationship.objects.get_or_create(
            from_profile=profile,
            to_profile=self.rel.student,
            kind=model.Relationship.KIND.elder,
            defaults={'description': relationship},
            )

        # send invite notifications
        if created:
            if email:
                invites.send_invite_email(
                    profile.user,
                    email_template_name='registration/invite_elder_email.txt',
                    subject_template_name='registration/invite_elder_subject.txt',
                    use_https=request.is_secure(),
                    extra_context={
                        'inviter': self.rel.elder,
                        'student': self.rel.student,
                        'inviter_rel': self.rel,
                        'invitee_rel': new_rel,
                        'domain': request.get_host(),
                        },
                    )
            else:
                invites.send_invite_sms(
                    profile.user,
                    template_name='registration/invite_elder_sms.txt',
                    extra_context={
                        'inviter': self.rel.elder,
                        'student': self.rel.student,
                        'inviter_rel': self.rel,
                        'invitee_rel': new_rel,
                        },
                    )

        return profile



class StudentForm(forms.ModelForm):
    """Form for editing a student."""
    groups = TemplateLabelModelMultipleChoiceField(
        queryset=model.Group.objects.none(),
        widget=GroupCheckboxSelectMultiple,
        required=False,
        )
    elders = TemplateLabelModelMultipleChoiceField(
        queryset=model.Profile.objects.none(),
        widget=ElderCheckboxSelectMultiple,
        required=False,
        )


    class Meta:
        model = model.Profile
        fields = ['name', 'groups', 'elders']


    def __init__(self, *args, **kwargs):
        """Store elder, set up group/elder choices and initial values."""
        self.elder = kwargs.pop('elder')
        super(StudentForm, self).__init__(*args, **kwargs)
        self.fields['groups'].queryset = model.Group.objects.filter(
            owner=self.elder)
        self.fields['elders'].queryset = model.Profile.objects.filter(
            school=self.elder.school, school_staff=True, deleted=False)
        if self.instance.pk:
            self.fields['groups'].initial = [
                g.pk for g in self.instance.student_in_groups.all()]
            self.fields['elders'].initial = [
                e.pk for e in self.direct_other_elders(self.instance)]


    def save(self):
        """Save and return student."""
        student = super(StudentForm, self).save()

        self.update_student_elders(student, self.cleaned_data['elders'])
        self.update_student_groups(student, self.cleaned_data['groups'])

        return student


    def direct_other_elders(self, student):
        """
        Get all direct (non-group) other-than-me elders of a student.

        Memoized by student id.

        """
        if not hasattr(self, '_direct_other_elders'):
            self._direct_other_elders = {}
        if self._direct_other_elders.get(student.pk) is None:
            self._direct_other_elders[student.pk] = [
                r.elder for r in
                model.Relationship.objects.filter(
                    to_profile=self.instance,
                    from_group=None,
                    from_profile__deleted=False,
                    ).exclude(
                    from_profile=self.elder).select_related('from_profile')
                ]
        return self._direct_other_elders[student.pk]


    def update_student_elders(self, student, elders):
        """
        Update student to have exactly given direct other-than-me elders.

        Excludes elder relationships due to group membership, and excludes the
        elder editing the student.

        """
        current = set(self.direct_other_elders(student))
        target = set(elders)
        remove = current.difference(target)
        add = target.difference(current)

        if remove:
            model.Relationship.objects.filter(
                to_profile=student,
                from_profile__in=remove,
                ).delete()

        for elder in add:
            model.Relationship.objects.get_or_create(
                to_profile=student,
                from_profile=elder,
                )


    def update_student_groups(self, student, groups):
        """Update student to be in exactly given groups."""
        student.student_in_groups = groups



class AddStudentForm(StudentForm):
    """Form for adding a student."""
    def save(self):
        """
        Save and return new student.

        Creates a relationship between the elder adding the student and the new
        student.

        """
        name = self.cleaned_data["name"]

        student = model.Profile.create_with_user(
            school=self.elder.school, name=name, invited_by=self.elder)

        self.update_student_elders(student, self.cleaned_data['elders'])
        self.update_student_groups(student, self.cleaned_data['groups'])

        model.Relationship.objects.create(
            from_profile=self.elder,
            to_profile=student,
            kind=model.Relationship.KIND.elder,
            )

        return student



class GroupForm(forms.ModelForm):
    """Form for editing Groups."""
    students = TemplateLabelModelMultipleChoiceField(
        queryset=model.Profile.objects.none(),
        widget=StudentCheckboxSelectMultiple,
        required=False,
        )
    elders = TemplateLabelModelMultipleChoiceField(
        queryset=model.Profile.objects.none(),
        widget=ElderCheckboxSelectMultiple,
        required=False,
        )


    class Meta:
        model = model.Group
        fields = ['name', 'students', 'elders']


    def __init__(self, *args, **kwargs):
        """Store owner, narrow student and elder choices appropriately."""
        instance = kwargs.get('instance', None)
        if instance:
            self.owner = instance.owner
        else:
            self.owner = kwargs.pop('owner')
        super(GroupForm, self).__init__(*args, **kwargs)
        self.fields['students'].queryset = model.Profile.objects.filter(
            relationships_to__from_profile=self.owner, deleted=False)
        self.fields['elders'].queryset = model.Profile.objects.filter(
            school=self.owner.school, school_staff=True, deleted=False)



class AddGroupForm(GroupForm):
    def save(self):
        """Save group, attaching new group to owner."""
        group = super(AddGroupForm, self).save(commit=False)
        group.owner = self.owner
        group.save()
        self.save_m2m()
        return group
