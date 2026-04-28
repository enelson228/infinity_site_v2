import pytest
from datetime import datetime


def test_add_and_list_forge_images(app):
    import database
    with app.app_context():
        img_id = database.add_forge_image('job-001', 'a red dragon', 'job-001.png', datetime.now().isoformat())
        assert isinstance(img_id, int)

        images = database.list_forge_images()
        assert len(images) == 1
        assert images[0]['job_id'] == 'job-001'
        assert images[0]['prompt'] == 'a red dragon'
        assert images[0]['filename'] == 'job-001.png'


def test_list_forge_images_newest_first(app):
    import database
    with app.app_context():
        database.add_forge_image('job-001', 'prompt one', 'job-001.png', '2026-01-01T00:00:00')
        database.add_forge_image('job-002', 'prompt two', 'job-002.png', '2026-01-02T00:00:00')

        images = database.list_forge_images()
        assert images[0]['job_id'] == 'job-002'
        assert images[1]['job_id'] == 'job-001'


def test_get_forge_image(app):
    import database
    with app.app_context():
        img_id = database.add_forge_image('job-003', 'a cat', 'job-003.png', datetime.now().isoformat())
        row = database.get_forge_image(img_id)
        assert row is not None
        assert row['job_id'] == 'job-003'


def test_get_forge_image_not_found(app):
    import database
    with app.app_context():
        assert database.get_forge_image(99999) is None


def test_get_forge_image_by_job_id(app):
    import database
    with app.app_context():
        database.add_forge_image('job-004', 'a ship', 'job-004.png', datetime.now().isoformat())
        row = database.get_forge_image_by_job_id('job-004')
        assert row is not None
        assert row['prompt'] == 'a ship'


def test_get_forge_image_by_job_id_not_found(app):
    import database
    with app.app_context():
        assert database.get_forge_image_by_job_id('nonexistent') is None


def test_delete_forge_image(app):
    import database
    with app.app_context():
        img_id = database.add_forge_image('job-005', 'a mountain', 'job-005.png', datetime.now().isoformat())
        database.delete_forge_image(img_id)
        assert database.get_forge_image(img_id) is None


def test_delete_forge_image_nonexistent(app):
    import database
    with app.app_context():
        # Should not raise
        database.delete_forge_image(99999)


def test_add_and_list_forge_videos(app):
    import database
    with app.app_context():
        video_id = database.add_forge_video('job-v001', 'a moving skyline', 'job-v001.mp4', datetime.now().isoformat())
        assert isinstance(video_id, int)

        videos = database.list_forge_videos()
        assert len(videos) == 1
        assert videos[0]['job_id'] == 'job-v001'
        assert videos[0]['filename'] == 'job-v001.mp4'


def test_get_and_delete_forge_video(app):
    import database
    with app.app_context():
        video_id = database.add_forge_video('job-v002', 'a moving skyline', 'job-v002.mp4', datetime.now().isoformat())
        row = database.get_forge_video(video_id)
        assert row is not None
        assert row['job_id'] == 'job-v002'
        assert database.get_forge_video_by_job_id('job-v002')['filename'] == 'job-v002.mp4'
        database.delete_forge_video(video_id)
        assert database.get_forge_video(video_id) is None
