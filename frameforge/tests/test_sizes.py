import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from PIL import Image
from app import frame_pipeline as frames, comfy_client, jobs
from app.models import AnimationCreateRequest, GenerateCharacterRequest


class SizesTests(unittest.TestCase):
    def test_canvas_crop_keeps_exact_subject_pixels(self):
        image = Image.new('RGBA', (1254, 1254))
        image.putpixel((700, 700), (231, 92, 23, 255))
        result = frames.fit_canvas_without_scaling(image, 1024)
        self.assertEqual(result.size, (1024, 1024))
        self.assertEqual(result.getpixel((585, 585)), (231, 92, 23, 255))

    def test_canvas_rejects_subject_clipping(self):
        image = Image.new('RGBA', (1254, 1254))
        image.putpixel((10, 10), (255, 0, 0, 255))
        with self.assertRaisesRegex(ValueError, 'clipping'):
            frames.fit_canvas_without_scaling(image, 1024)

    def test_frames_retain_positions_and_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.png'
            image = Image.new('RGBA', (512, 512))
            image.putpixel((70, 81), (255, 70, 20, 255))
            image.save(source)
            with patch.object(Image.Image, 'resize', side_effect=AssertionError('resampling')):
                paths = frames.process_animation_frames([source], root / 'frames', 512, preserve_canvas=True)
            result = Image.open(paths[0])
            self.assertEqual(result.size, (512, 512))
            self.assertEqual(result.getpixel((70, 81)), (255, 70, 20, 255))
            with self.assertRaisesRegex(ValueError, 'differs'):
                frames.process_animation_frames([source], root / 'bad', 1024, preserve_canvas=True)

    def test_wan_source_rejects_resize_in_strict_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.png'
            Image.new('RGB', (512, 512)).save(source)
            with patch.object(Image.Image, 'resize', side_effect=AssertionError('resampling')):
                comfy_client._prepare_wan_input(source, root / 'wan.png', 512, 512, no_scale=True)
            with self.assertRaisesRegex(ValueError, 'expected'):
                comfy_client._prepare_wan_input(source, root / 'bad.png', 1024, 1024, no_scale=True)

    def test_api_accepts_new_sizes_and_rejects_mismatched_strict_jobs(self):
        self.assertEqual(GenerateCharacterRequest(prompt='cat', pixel_size=1024).pixel_size, 1024)
        self.assertEqual(AnimationCreateRequest(anim_type='idle', wan_size=512).wan_size, 512)
        with patch.object(jobs.storage, 'load_meta', return_value={'pixel_size': 512}):
            with self.assertRaisesRegex(ValueError, 'equal'):
                jobs.start_animation_job(character_id='example', wan_size=1024, no_scale=True)


if __name__ == '__main__':
    unittest.main()
