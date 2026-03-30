from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('news', '0002_alter_newsletter_author'),
    ]

    operations = [
        migrations.AddField(
            model_name='article',
            name='section',
            field=models.CharField(
                choices=[
                    ('politics', 'Politics'),
                    ('trending', 'Trending'),
                    ('sports', 'Sports'),
                    ('social_media', 'Social Media'),
                    ('weather', 'Weather'),
                    ('religion', 'Religion'),
                ],
                default='trending',
                max_length=20,
            ),
        ),
    ]
