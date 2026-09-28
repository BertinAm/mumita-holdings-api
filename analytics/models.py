from django.db import models


class Device(models.TextChoices):
    MOBILE = 'mobile', 'Mobile'
    TABLET = 'tablet', 'Tablet'
    DESKTOP = 'desktop', 'Desktop'


class DailyVisit(models.Model):
    """One row per day, path, country, referrer host and device, with a page
    view count. No IP, no cookie, no user id: only this aggregate is kept."""

    date = models.DateField(db_index=True)
    path = models.CharField(max_length=300)
    country = models.CharField(max_length=2, blank=True, help_text='ISO 3166-1 alpha-2, from Cloudflare.')
    referrer_host = models.CharField(max_length=120, blank=True)
    device = models.CharField(max_length=10, choices=Device.choices)
    views = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-date', '-views']
        constraints = [
            models.UniqueConstraint(
                fields=['date', 'path', 'country', 'referrer_host', 'device'], name='analytics_daily_visit_key'
            ),
        ]

    def __str__(self):
        return f'{self.date} {self.path} {self.views}'
