import unittest

from directories import DirectoryMap
from sync import copy


def snapshot(sid, directory, updated=1, title='Some title'):
    return {'info': {'id': sid, 'title': title, 'location': {'directory': directory}, 'time': {'updated': updated}}, 'messages': []}


class FakeSource:
    def __init__(self, snapshots):
        self._snapshots = snapshots

    def export_session(self, sid):
        return self._snapshots[sid]


class FakeTarget:
    def __init__(self, existing_directories=()):
        self.existing_directories = set(existing_directories)
        self.probed = []
        self.imported = []

    def has_directory(self, directory):
        self.probed.append(directory)
        return directory in self.existing_directories

    def import_session(self, snapshot, directory):
        self.imported.append((snapshot['info']['id'], directory))
        return {'time': {'updated': 2}}


class CopyDirectoryTests(unittest.TestCase):
    def test_unmapped_directory_is_kept(self):
        source, target = FakeSource({'ses_a': snapshot('ses_a', '/tmp/research')}), FakeTarget({'/tmp/research'})
        resolve = DirectoryMap.parse({}).to_hub
        with self.assertNoLogs('opencode-sess-sync', level='WARNING'):
            synced = copy('push', source, target, {'ses_a': {}}, {}, {'ses_a'}, resolve)
        self.assertEqual(target.imported, [('ses_a', '/tmp/research')])
        self.assertEqual(synced, {'ses_a': (1, 2)})

    def test_probe_and_import_use_mapped_directory(self):
        source, target = FakeSource({'ses_a': snapshot('ses_a', '/home/me/x')}), FakeTarget({'/home/hub/x'})
        resolve = DirectoryMap.parse({'/home/me/*': '/home/hub/*'}).to_hub
        with self.assertNoLogs('opencode-sess-sync', level='WARNING'):
            copy('push', source, target, {'ses_a': {}}, {}, {'ses_a'}, resolve)
        self.assertEqual(target.probed, ['/home/hub/x'])
        self.assertEqual(target.imported, [('ses_a', '/home/hub/x')])

    def test_missing_directory_warns_but_still_imports(self):
        source, target = FakeSource({'ses_a': snapshot('ses_a', '/nope')}), FakeTarget()
        resolve = DirectoryMap.parse({}).to_hub
        with self.assertLogs('opencode-sess-sync', level='WARNING') as logs:
            copy('pull', source, target, {'ses_a': {}}, {}, {'ses_a'}, resolve)
        self.assertEqual(target.imported, [('ses_a', '/nope')])
        self.assertEqual(len(logs.output), 1)
        self.assertIn('pull', logs.output[0])
        self.assertIn('ses_a', logs.output[0])
        self.assertIn('/nope', logs.output[0])

    def test_probe_is_cached_per_directory(self):
        snapshots = {'ses_a': snapshot('ses_a', '/same'), 'ses_b': snapshot('ses_b', '/same')}
        source, target = FakeSource(snapshots), FakeTarget({'/same'})
        resolve = DirectoryMap.parse({}).to_hub
        copy('push', source, target, snapshots, {}, {'ses_a', 'ses_b'}, resolve)
        self.assertEqual(target.probed, ['/same'])


if __name__ == '__main__':
    unittest.main()
