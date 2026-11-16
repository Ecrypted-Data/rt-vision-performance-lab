import unittest

import numpy as np

from vision.pipeline import threshold


class ThresholdTests(unittest.TestCase):
    @staticmethod
    def reference(gray, cutoff):
        result = np.zeros_like(gray)
        for y in range(gray.shape[0]):
            for x in range(gray.shape[1]):
                if int(gray[y, x]) >= cutoff:
                    result[y, x] = 255
        return result

    def test_cutoff_is_inclusive(self):
        image = np.array([[0, 159, 160, 161, 255]], dtype=np.uint8)
        original = image.copy()
        result = threshold(image)
        np.testing.assert_array_equal(result, [[0, 0, 255, 255, 255]])
        self.assertEqual(result.dtype, image.dtype)
        np.testing.assert_array_equal(image, original)

    def test_matches_scalar_reference(self):
        image = np.random.default_rng(42).integers(0, 256, (37, 43), dtype=np.uint8)
        for cutoff in (-1, 0, 1, 159, 160, 255, 256):
            with self.subTest(cutoff=cutoff):
                np.testing.assert_array_equal(threshold(image, cutoff), self.reference(image, cutoff))

    def test_non_contiguous_view_and_empty_array(self):
        image = np.arange(100, dtype=np.uint8).reshape(10, 10)[::2, ::2]
        np.testing.assert_array_equal(threshold(image, 40), self.reference(image, 40))
        empty = np.empty((0, 7), dtype=np.uint8)
        self.assertEqual(threshold(empty).shape, (0, 7))


if __name__ == '__main__':
    unittest.main()
