from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models

from common.models import Publishable


class Department(models.TextChoices):
    """Frontend keys for the five department marks (VECTORS-AND-MOTION.md).
    The mark itself is an SVG in the frontend, not stored here."""

    AGRIC_CONSULTANCY = 'agric-consultancy', 'Agric Consultancy'
    FOOD_PROCESSING = 'food-processing', 'Food Processing'
    NUTRITION = 'nutrition', 'Nutrition'
    IT = 'it', 'IT'
    HR = 'hr', 'HR'


class TeamMember(Publishable):
    """SITEMAP §5 people.TeamMember.

    NO PHOTO FIELD, BY DESIGN (Review §7: no individual face photographs in
    team profiles). Do not add an image field here; tests assert its absence.
    A member is shown only when published AND consent_to_publish is true.
    """

    class Tier(models.TextChoices):
        EXECUTIVE = 'executive', 'Executive'
        ADVISORY = 'advisory', 'Advisory board'
        MENTOR = 'mentor', 'Mentor'
        OPERATIONS = 'operations', 'Operations'

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, unique=True)
    qualification = models.CharField(max_length=160, blank=True, help_text='Highest qualification.')
    years_experience = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(70)]
    )
    department = models.CharField(max_length=20, choices=Department.choices)
    tier = models.CharField(max_length=12, choices=Tier.choices, default=Tier.OPERATIONS)
    value_statement = models.TextField(blank=True, help_text='Two or three sentences.')
    consent_to_publish = models.BooleanField(
        default=False, help_text='Written consent received. Required before the profile is shown.'
    )
    is_blog_author = models.BooleanField(default=False)

    class Meta(Publishable.Meta):
        pass

    def __str__(self):
        return self.name


class Partner(Publishable):
    """SITEMAP §5 people.Partner. Shown only when published AND
    permission_to_display is true."""

    class Tier(models.TextChoices):
        INSTITUTIONAL = 'institutional', 'Development and institutional'
        BUYER = 'buyer', 'Buyers and distribution'

    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=80, unique=True)
    tier = models.CharField(max_length=14, choices=Tier.choices)
    logo = models.FileField(
        upload_to='partners/', blank=True,
        validators=[FileExtensionValidator(['svg', 'png', 'webp'])],
        help_text="The partner's own mark. Monochrome treatment is applied by the frontend.",
    )
    url = models.URLField(blank=True)
    relationship = models.CharField(
        max_length=240, blank=True, help_text='The real relationship: award, grant, programme, stockist.'
    )
    since_year = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(2000), MaxValueValidator(2100)]
    )
    permission_to_display = models.BooleanField(default=False)

    class Meta(Publishable.Meta):
        pass

    def __str__(self):
        return self.name


class Region(Publishable):
    """SITEMAP §5 people.Region: the five regions on the map."""

    key = models.SlugField(max_length=30, unique=True, help_text='Frontend region key.')
    name = models.CharField(max_length=60)
    note = models.CharField(max_length=25, blank=True, help_text='Map pin label, 25 characters maximum.')
    geo_key = models.CharField(max_length=60, help_text='Region name in the frontend map geometry.')

    class Meta(Publishable.Meta):
        pass

    def __str__(self):
        return self.name
