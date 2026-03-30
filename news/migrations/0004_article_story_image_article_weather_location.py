from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('news', '0003_article_section'),
    ]

    operations = [
        migrations.AddField(
            model_name='article',
            name='story_image',
            field=models.ImageField(blank=True, null=True, upload_to='article_images/'),
        ),
        migrations.AddField(
            model_name='article',
            name='weather_location',
            field=models.CharField(
                blank=True,
                help_text='Optional location for auto-generated weather updates.',
                max_length=120,
            ),
        ),
    ]
