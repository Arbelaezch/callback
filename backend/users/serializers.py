from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Resume, CoverLetterTemplate
from jobs.models import JobSearch

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ('username', 'email', 'password')

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
        )


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'created_at')
        read_only_fields = ('id', 'created_at')

        # SOCIAL AUTH SCAFFOLD:
        # Add 'avatar_url', 'provider' fields to CustomUser and include here


class ResumeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resume
        fields = ('id', 'filename', 'status', 'is_default', 'uploaded_at')
        read_only_fields = ('id', 'filename', 'is_default', 'uploaded_at')


class CoverLetterTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoverLetterTemplate
        fields = ('id', 'label', 'body', 'is_default', 'created_at')
        read_only_fields = ('id', 'is_default', 'created_at')


class JobSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobSearch
        fields = (
            'id',
            'label',
            'role_titles',
            'cities',
            'location_types',
            'seniority_levels',
            'years_experience',
            'salary_min',
            'excluded_companies',
            'daily_limit',
            'active',
            'created_at',
        )
        read_only_fields = ('id', 'active', 'created_at')


class OnboardingSerializer(serializers.Serializer):
    """
    Accepts all onboarding data in one submission:
    resume file + cover letter + job search preferences.
    """
    # Resume
    resume = serializers.FileField()

    # Cover letter
    cover_letter_label = serializers.CharField(max_length=100, default='Default')
    cover_letter_body = serializers.CharField()

    # Job search
    label = serializers.CharField(max_length=100, required=False, default='')
    role_titles = serializers.ListField(
        child=serializers.CharField(max_length=100), min_length=1
    )
    cities = serializers.ListField(
        child=serializers.CharField(max_length=100), required=False, default=list
    )
    location_types = serializers.ListField(
        child=serializers.CharField(max_length=10), required=False, default=list
    )
    seniority_levels = serializers.ListField(
        child=serializers.CharField(max_length=15), required=False, default=list
    )
    years_experience = serializers.IntegerField(required=False, allow_null=True)
    salary_min = serializers.IntegerField(required=False, allow_null=True)
    excluded_companies = serializers.ListField(
        child=serializers.CharField(max_length=200), required=False, default=list
    )

    def validate_resume(self, file):
        if not file.name.endswith('.pdf'):
            raise serializers.ValidationError('Resume must be a PDF.')
        if file.size > 5 * 1024 * 1024:  # 5MB
            raise serializers.ValidationError('Resume must be under 5MB.')
        return file