from unittest import TestCase

from mock import Mock, patch
from yum import constants
from yum.callbacks import PT_MESSAGES
from yum.Errors import InstallError, GroupsError

from pulp_rpm.handlers.rpmtools import Package, PackageGroup
from pulp_rpm.handlers.rpmtools import ProgressReport
from pulp_rpm.handlers.rpmtools import ProcessTransCallback, RPMCallback, DownloadCallback, Yum


class Pkg:

    def __init__(self, name, version, release='1', arch='noarch'):
        self.name = name
        self.ver = version
        self.rel = str(release)
        self.arch = arch
        self.epoch = '0'

    def __str__(self):
        if int(self.epoch) > 0:
            format = '%(epoch)s:%(name)s-%(ver)s-%(rel)s.%(arch)s'
        else:
            format = '%(name)s-%(ver)s-%(rel)s.%(arch)s'
        return format % self.__dict__


class TxMember:

    def __init__(self, state, pkg, repo_id='fedora', is_dep=False):
        self.output_state = state
        self.repoid = repo_id
        self.isDep = is_dep
        self.po = pkg


class TestPackage(TestCase):

    def test_tx_summary(self):
        deps = [
            TxMember(constants.TS_INSTALL, Pkg('D1', '1.0'), is_dep=True),
            TxMember(constants.TS_INSTALL, Pkg('D2', '1.0'), is_dep=True),
            TxMember(constants.TS_INSTALL, Pkg('D3', '1.0'), is_dep=True),
        ]
        install = [
            TxMember(constants.TS_INSTALL, Pkg('A', '1.0')),
            TxMember(constants.TS_INSTALL, Pkg('B', '1.0')),
            TxMember(constants.TS_INSTALL, Pkg('C', '1.0')),
        ]
        erase = [
            TxMember(constants.TS_ERASE, Pkg('D', '1.0')),
        ]
        failed = [
            TxMember(constants.TS_FAILED, Pkg('E', '1.0')),
            TxMember(constants.TS_FAILED, Pkg('F', '1.0')),
        ]
        ts_info = install + deps + erase + failed
        package = Package()
        states = [constants.TS_FAILED, constants.TS_INSTALL]

        # test

        report = package.tx_summary(ts_info, states)

        # validation

        _resolved = [
            {'epoch': '0', 'version': '1.0', 'name': 'A', 'release': '1',
             'arch': 'noarch', 'qname': 'A-1.0-1.noarch', 'repoid': 'fedora'},
            {'epoch': '0', 'version': '1.0', 'name': 'B', 'release': '1',
             'arch': 'noarch', 'qname': 'B-1.0-1.noarch', 'repoid': 'fedora'},
            {'epoch': '0', 'version': '1.0', 'name': 'C', 'release': '1',
             'arch': 'noarch', 'qname': 'C-1.0-1.noarch', 'repoid': 'fedora'},
            {'epoch': '0', 'version': '1.0', 'name': 'E', 'release': '1',
             'arch': 'noarch', 'qname': 'E-1.0-1.noarch', 'repoid': 'fedora'},
            {'epoch': '0', 'version': '1.0', 'name': 'F', 'release': '1',
             'arch': 'noarch', 'qname': 'F-1.0-1.noarch', 'repoid': 'fedora'},
        ]
        _failed = [
            {'epoch': '0', 'version': '1.0', 'name': 'E', 'release': '1',
             'arch': 'noarch', 'qname': 'E-1.0-1.noarch', 'repoid': 'fedora'},
            {'epoch': '0', 'version': '1.0', 'name': 'F', 'release': '1',
             'arch': 'noarch', 'qname': 'F-1.0-1.noarch', 'repoid': 'fedora'},
        ]
        _deps = [
            {'epoch': '0', 'version': '1.0', 'name': 'D1', 'release': '1',
             'arch': 'noarch', 'qname': 'D1-1.0-1.noarch', 'repoid': 'fedora'},
            {'epoch': '0', 'version': '1.0', 'name': 'D2', 'release': '1',
             'arch': 'noarch', 'qname': 'D2-1.0-1.noarch', 'repoid': 'fedora'},
            {'epoch': '0', 'version': '1.0', 'name': 'D3', 'release': '1',
             'arch': 'noarch', 'qname': 'D3-1.0-1.noarch', 'repoid': 'fedora'},
        ]

        self.assertEqual(report['resolved'], _resolved)
        self.assertEqual(report['deps'], _deps)
        self.assertEqual(report['failed'], _failed)

    @patch('pulp_rpm.handlers.rpmtools.Package.tx_summary')
    def test_installed(self, fake_summary):
        fake_summary.return_value = Mock()
        ts_info = Mock()

        # test
        report = Package.installed(ts_info)

        # validation
        fake_summary.assert_called_with(
            ts_info, (constants.TS_FAILED, constants.TS_INSTALL, constants.TS_UPDATE))
        self.assertEqual(report, fake_summary())

    @patch('pulp_rpm.handlers.rpmtools.Package.tx_summary')
    def test_updated(self, fake_summary):
        fake_summary.return_value = Mock()
        ts_info = Mock()

        # test
        report = Package.updated(ts_info)

        # validation
        fake_summary.assert_called_with(
            ts_info, (constants.TS_FAILED, constants.TS_INSTALL, constants.TS_UPDATE))
        self.assertEqual(report, fake_summary())

    @patch('pulp_rpm.handlers.rpmtools.Package.tx_summary')
    def test_erased(self, fake_summary):
        fake_summary.return_value = Mock()
        ts_info = Mock()

        # test
        report = Package.erased(ts_info)

        # validation
        fake_summary.assert_called_with(
            ts_info, (constants.TS_FAILED, constants.TS_ERASE))
        self.assertEqual(report, fake_summary())

    def test_construction(self):
        # test
        package = Package()

        # validation
        self.assertTrue(package.apply)
        self.assertFalse(package.importkeys)
        self.assertEqual(package.progress, None)

        # test
        apply = Mock()
        importkeys = Mock()
        progress = Mock()
        package = Package(apply=apply, importkeys=importkeys, progress=progress)

        # validation
        self.assertEqual(package.apply, apply)
        self.assertEqual(package.importkeys, importkeys)
        self.assertEqual(package.progress, progress)


class TestPackageInstall(TestCase):

    @patch('pulp_rpm.handlers.rpmtools.Package.tx_summary')
    @patch('pulp_rpm.handlers.rpmtools.Yum')
    def test_install(self, FakeYum, fake_summary):
        resolved = [
            Pkg('openssl', '3.2'),
            Pkg('libc', '6.7'),
        ]
        ts_info = [TxMember(constants.TS_INSTALL, p) for p in resolved]
        fake_yum = Mock()
        fake_yum.tsInfo = ts_info
        FakeYum.return_value = fake_yum
        fake_summary.return_value = Mock()
        names = [p.name for p in resolved]
        progress = Mock()

        # test
        package = Package(progress=progress)
        report = package.install(names)

        # validation
        self.assertEqual(fake_yum.install.call_count, len(names))
        FakeYum.assert_called_with(package.importkeys, package.progress)
        for n, call in enumerate(fake_yum.install.call_args_list):
            self.assertEqual(call[1], dict(pattern=names[n]))
        self.assertEqual(report, fake_summary())
        self.assertTrue(fake_yum.processTransaction.called)
        self.assertTrue(fake_yum.close.called)

    @patch('pulp_rpm.handlers.rpmtools.Package.tx_summary')
    @patch('pulp_rpm.handlers.rpmtools.Yum')
    def test_nothing_applied(self, FakeYum, fake_summary):
        resolved = [
            Pkg('openssl', '3.2'),
            Pkg('libc', '6.7'),
        ]
        ts_info = [TxMember(constants.TS_INSTALL, p) for p in resolved]
        fake_yum = Mock()
        fake_yum.tsInfo = ts_info
        FakeYum.return_value = fake_yum
        fake_summary.return_value = Mock()
        names = [p.name for p in resolved]

        # test
        package = Package(apply=False)
        report = package.install(names)

        # validation
        self.assertEqual(fake_yum.install.call_count, len(names))
        FakeYum.assert_called_with(package.importkeys, None)
        for n, call in enumerate(fake_yum.install.call_args_list):
            self.assertEqual(call[1], dict(pattern=names[n]))
        self.assertEqual(report, fake_summary())
        self.assertFalse(fake_yum.processTransaction.called)
        self.assertTrue(fake_yum.close.called)

    @patch('pulp_rpm.handlers.rpmtools.Yum')
    def test_import_keys(self, FakeYum):
        # test
        package = Package(importkeys=True)
        package.install([])

        # validation
        FakeYum.assert_called_with(package.importkeys, None)

    @patch('pulp_rpm.handlers.rpmtools.Yum')
    def test_nothing_matched(self, FakeYum):
        fake_yum = Mock()
        fake_yum.install.side_effect = InstallError()
        FakeYum.return_value = fake_yum

        # test
        package = Package()
        self.assertRaises(InstallError, package.install, ['openssl'])
        self.assertFalse(fake_yum.processTransaction.called)
        self.assertTrue(fake_yum.close.called)


class TestPackageUpdate(TestCase):

    @patch('pulp_rpm.handlers.rpmtools.Package.tx_summary')
    @patch('pulp_rpm.handlers.rpmtools.Yum')
    def test_update(self, FakeYum, fake_summary):
        resolved = [
            Pkg('openssl', '3.2'),
            Pkg('libc', '6.7'),
        ]
        ts_info = [TxMember(constants.TS_UPDATE, p) for p in resolved]
        fake_yum = Mock()
        fake_yum.tsInfo = ts_info
        FakeYum.return_value = fake_yum
        fake_summary.return_value = Mock()
        names = [p.name for p in resolved]
        progress = Mock()

        # test
        package = Package(progress=progress)
        report = package.update(names)

        # validation
        self.assertEqual(fake_yum.update.call_count, len(names))
        FakeYum.assert_called_with(package.importkeys, package.progress)
        for n, call in enumerate(fake_yum.update.call_args_list):
            self.assertEqual(call[1], dict(pattern=names[n]))
        self.assertEqual(report, fake_summary())
        self.assertTrue(fake_yum.processTransaction.called)
        self.assertTrue(fake_yum.close.called)

    @patch('pulp_rpm.handlers.rpmtools.Package.tx_summary')
    @patch('pulp_rpm.handlers.rpmtools.Yum')
    def test_nothing_applied(self, FakeYum, fake_summary):
        resolved = [
            Pkg('openssl', '3.2'),
            Pkg('libc', '6.7'),
        ]
        ts_info = [TxMember(constants.TS_INSTALL, p) for p in resolved]
        fake_yum = Mock()
        fake_yum.tsInfo = ts_info
        FakeYum.return_value = fake_yum
        fake_summary.return_value = Mock()
        names = [p.name for p in resolved]

        # test
        package = Package(apply=False)
        report = package.update(names)

        # validation
        self.assertEqual(fake_yum.update.call_count, len(names))
        FakeYum.assert_called_with(package.importkeys, None)
        for n, call in enumerate(fake_yum.update.call_args_list):
            self.assertEqual(call[1], dict(pattern=names[n]))
        self.assertEqual(report, fake_summary())
        self.assertFalse(fake_yum.processTransaction.called)
        self.assertTrue(fake_yum.close.called)

    @patch('pulp_rpm.handlers.rpmtools.Yum')
    def test_import_keys(self, FakeYum):
        # test
        package = Package(importkeys=True)
        package.update([])

        # validation
        FakeYum.assert_called_with(package.importkeys, None)


class TestPackageUninstall(TestCase):

    @patch('pulp_rpm.handlers.rpmtools.Package.tx_summary')
    @patch('pulp_rpm.handlers.rpmtools.Yum')
    def test_uninstall(self, FakeYum, fake_summary):
        resolved = [
            Pkg('openssl', '3.2'),
            Pkg('libc', '6.7'),
        ]
        ts_info = [TxMember(constants.TS_UPDATE, p) for p in resolved]
        fake_yum = Mock()
        fake_yum.tsInfo = ts_info
        FakeYum.return_value = fake_yum
        fake_summary.return_value = Mock()
        names = [p.name for p in resolved]
        progress = Mock()

        # test
        package = Package(progress=progress)
        report = package.uninstall(names)

        # validation
        self.assertEqual(fake_yum.remove.call_count, len(names))
        FakeYum.assert_called_with(progress=package.progress)
        for n, call in enumerate(fake_yum.remove.call_args_list):
            self.assertEqual(call[1], dict(pattern=names[n]))
        self.assertEqual(report, fake_summary())
        self.assertTrue(fake_yum.processTransaction.called)
        self.assertTrue(fake_yum.close.called)

    @patch('pulp_rpm.handlers.rpmtools.Package.tx_summary')
    @patch('pulp_rpm.handlers.rpmtools.Yum')
    def test_nothing_applied(self, FakeYum, fake_summary):
        resolved = [
            Pkg('openssl', '3.2'),
            Pkg('libc', '6.7'),
        ]
        ts_info = [TxMember(constants.TS_INSTALL, p) for p in resolved]
        fake_yum = Mock()
        fake_yum.tsInfo = ts_info
        FakeYum.return_value = fake_yum
        fake_summary.return_value = Mock()
        names = [p.name for p in resolved]

        # test
        package = Package(apply=False)
        report = package.uninstall(names)

        # validation
        self.assertEqual(fake_yum.remove.call_count, len(names))
        FakeYum.assert_called_with(progress=None)
        for n, call in enumerate(fake_yum.remove.call_args_list):
            self.assertEqual(call[1], dict(pattern=names[n]))
        self.assertEqual(report, fake_summary())
        self.assertFalse(fake_yum.processTransaction.called)
        self.assertTrue(fake_yum.close.called)


class TestPackageGroup(TestCase):

    def test_construction(self):
        # test
        group = PackageGroup()

        # validation
        self.assertTrue(group.apply)
        self.assertFalse(group.importkeys)
        self.assertEqual(group.progress, None)

        # test
        apply = Mock()
        importkeys = Mock()
        progress = Mock()
        group = PackageGroup(apply=apply, importkeys=importkeys, progress=progress)

        # validation
        self.assertEqual(group.apply, apply)
        self.assertEqual(group.importkeys, importkeys)
        self.assertEqual(group.progress, progress)


class TestGroupInstall(TestCase):

    @patch('pulp_rpm.handlers.rpmtools.Package.tx_summary')
    @patch('pulp_rpm.handlers.rpmtools.Yum')
    def test_install(self, FakeYum, fake_summary):
        resolved = [
            Pkg('openssl', '3.2'),
            Pkg('libc', '6.7'),
        ]
        ts_info = [TxMember(constants.TS_INSTALL, p) for p in resolved]
        fake_yum = Mock()
        fake_yum.tsInfo = ts_info
        FakeYum.return_value = fake_yum
        fake_summary.return_value = Mock()
        names = ['security']
        progress = Mock()

        # test
        group = PackageGroup(progress=progress)
        report = group.install(names)

        # validation
        self.assertEqual(fake_yum.selectGroup.call_count, len(names))
        FakeYum.assert_called_with(group.importkeys, group.progress)
        for n, call in enumerate(fake_yum.selectGroup.call_args_list):
            self.assertEqual(call[0], (names[n],))
        self.assertEqual(report, fake_summary())
        self.assertTrue(fake_yum.processTransaction.called)
        self.assertTrue(fake_yum.close.called)

    @patch('pulp_rpm.handlers.rpmtools.Package.tx_summary')
    @patch('pulp_rpm.handlers.rpmtools.Yum')
    def test_nothing_applied(self, FakeYum, fake_summary):
        resolved = [
            Pkg('openssl', '3.2'),
            Pkg('libc', '6.7'),
        ]
        ts_info = [TxMember(constants.TS_INSTALL, p) for p in resolved]
        fake_yum = Mock()
        fake_yum.tsInfo = ts_info
        FakeYum.return_value = fake_yum
        fake_summary.return_value = Mock()
        names = [p.name for p in resolved]

        # test
        group = PackageGroup(apply=False)
        report = group.install(names)

        # validation
        self.assertEqual(fake_yum.selectGroup.call_count, len(names))
        FakeYum.assert_called_with(group.importkeys, group.progress)
        for n, call in enumerate(fake_yum.selectGroup.call_args_list):
            self.assertEqual(call[0], (names[n],))
        self.assertEqual(report, fake_summary())
        self.assertFalse(fake_yum.processTransaction.called)
        self.assertTrue(fake_yum.close.called)

    @patch('pulp_rpm.handlers.rpmtools.Yum')
    def test_import_keys(self, FakeYum):
        # test
        group = PackageGroup(importkeys=True)
        group.install([])

        # validation
        FakeYum.assert_called_with(group.importkeys, None)

    @patch('pulp_rpm.handlers.rpmtools.Yum')
    def test_nothing_matched(self, FakeYum):
        fake_yum = Mock()
        fake_yum.selectGroup.side_effect = GroupsError()
        FakeYum.return_value = fake_yum

        # test
        group = PackageGroup()
        self.assertRaises(GroupsError, group.install, ['nothing'])
        self.assertFalse(fake_yum.processTransaction.called)
        self.assertTrue(fake_yum.close.called)


class TestGroupUninstall(TestCase):

    @patch('pulp_rpm.handlers.rpmtools.Package.tx_summary')
    @patch('pulp_rpm.handlers.rpmtools.Yum')
    def test_uninstall(self, FakeYum, fake_summary):
        resolved = [
            Pkg('openssl', '3.2'),
            Pkg('libc', '6.7'),
        ]
        ts_info = [TxMember(constants.TS_INSTALL, p) for p in resolved]
        fake_yum = Mock()
        fake_yum.tsInfo = ts_info
        FakeYum.return_value = fake_yum
        fake_summary.return_value = Mock()
        names = ['security']
        progress = Mock()

        # test
        group = PackageGroup(progress=progress)
        report = group.uninstall(names)

        # validation
        self.assertEqual(fake_yum.groupRemove.call_count, len(names))
        FakeYum.assert_called_with(progress=group.progress)
        for n, call in enumerate(fake_yum.groupRemove.call_args_list):
            self.assertEqual(call[0], (names[n],))
        self.assertEqual(report, fake_summary())
        self.assertTrue(fake_yum.processTransaction.called)
        self.assertTrue(fake_yum.close.called)

    @patch('pulp_rpm.handlers.rpmtools.Package.tx_summary')
    @patch('pulp_rpm.handlers.rpmtools.Yum')
    def test_nothing_applied(self, FakeYum, fake_summary):
        resolved = [
            Pkg('openssl', '3.2'),
            Pkg('libc', '6.7'),
        ]
        ts_info = [TxMember(constants.TS_INSTALL, p) for p in resolved]
        fake_yum = Mock()
        fake_yum.tsInfo = ts_info
        FakeYum.return_value = fake_yum
        fake_summary.return_value = Mock()
        names = ['security']

        # test
        group = PackageGroup(apply=False)
        report = group.uninstall(names)

        # validation
        self.assertEqual(fake_yum.groupRemove.call_count, len(names))
        FakeYum.assert_called_with(progress=group.progress)
        for n, call in enumerate(fake_yum.groupRemove.call_args_list):
            self.assertEqual(call[0], (names[n],))
        self.assertEqual(report, fake_summary())
        self.assertFalse(fake_yum.processTransaction.called)
        self.assertTrue(fake_yum.close.called)

    @patch('pulp_rpm.handlers.rpmtools.Yum')
    def test_nothing_matched(self, FakeYum):
        fake_yum = Mock()
        fake_yum.groupRemove.side_effect = GroupsError()
        FakeYum.return_value = fake_yum

        # test
        group = PackageGroup()
        self.assertRaises(GroupsError, group.uninstall, ['nothing'])
        self.assertFalse(fake_yum.processTransaction.called)
        self.assertTrue(fake_yum.close.called)


class TestProgressReport(TestCase):

    def test_construction(self):
        # test
        pr = ProgressReport()

        # validation
        self.assertEqual(pr.steps, [])
        self.assertEqual(pr.details, {})

    @patch('pulp_rpm.handlers.rpmtools.ProgressReport._updated')
    @patch('pulp_rpm.handlers.rpmtools.ProgressReport.set_status')
    def test_push_step(self, fake_set_status, fake_updated):
        step = 'started'

        # test
        pr = ProgressReport()
        pr.push_step(step)

        # validation
        fake_updated.assert_called_with()
        fake_set_status.assert_called_with(ProgressReport.SUCCEEDED)
        self.assertEqual(pr.steps, [[step, ProgressReport.PENDING]])
        self.assertEqual(pr.details, {})

    @patch('pulp_rpm.handlers.rpmtools.ProgressReport._updated')
    def test_set_status(self, fake_updated):
        step = 'started'

        # test
        pr = ProgressReport()
        pr.push_step(step)
        pr.set_status(True)

        # validation
        self.assertEqual(pr.steps, [[step, True]])
        self.assertEqual(pr.details, {})
        self.assertTrue(fake_updated.called)

    @patch('pulp_rpm.handlers.rpmtools.ProgressReport._updated')
    def test_set_status_no_steps(self, fake_updated):
        pr = ProgressReport()
        pr.set_status(True)

        # validation
        self.assertEqual(pr.steps, [])
        self.assertEqual(pr.details, {})
        self.assertFalse(fake_updated.called)

    @patch('pulp_rpm.handlers.rpmtools.ProgressReport._updated')
    def test_set_action(self, _updated):
        package = 'openssl'
        action = '100'

        # test
        pr = ProgressReport()
        pr.set_action(action, package)

        # validation
        self.assertEqual(pr.details, dict(action=action, package=package))
        self.assertTrue(_updated.called)

    @patch('pulp_rpm.handlers.rpmtools.ProgressReport._updated')
    def test_error(self, fake_updated):
        step = 'started'
        message = 'This is bad'

        # test
        pr = ProgressReport()
        pr.push_step(step)
        pr.error(message)

        # validation
        self.assertEqual(pr.details, dict(error=message))
        self.assertEqual(pr.steps, [[step, False]])
        self.assertTrue(fake_updated.called)


class TestProgressReporting(TestCase):

    def test_reporting(self):
        steps = ('A', 'B', 'C')
        action = ('downloading', 'package-xyz-1.0-1.f16.rpm')
        pr = ProgressReport()
        pr._updated = Mock()
        for s in steps:
            # validate steps pushed with status of None
            pr.push_step(s)
            name, status = pr.steps[-1]
            self.assertEqual(name, s)
            self.assertTrue(status is None)
            # validate details cleared on state pushed
            self.assertEqual(len(pr.details), 0)
            # set the action
            pr.set_action(action[0], action[1])
            # validate action
            self.assertEqual(pr.details['action'], action[0])
            self.assertEqual(pr.details['package'], action[1])
            # validate previous step status is set (True) on next
            # push when status is None
            prev = pr.steps[-2:-1]
            if prev:
                self.assertTrue(prev[0][1])

    def test_reporting_with_errors(self):
        # Test that previous state with status=False is not
        # set (True) on next state push
        steps = ('A', 'B', 'C')
        pr = ProgressReport()
        pr._updated = Mock()
        pr.push_step(steps[0])
        pr.push_step(steps[1])
        pr.set_status(False)
        pr.push_step(steps[2])
        self.assertTrue(pr.steps[0][1])
        self.assertFalse(pr.steps[1][1])
        self.assertTrue(pr.steps[2][1] is None)


class TestTransactionCallback(TestCase):

    def test_construction(self):
        pr = ProgressReport()
        cb = ProcessTransCallback(pr)
        self.assertEqual(cb.report, pr)

    @patch('pulp_rpm.handlers.rpmtools.ProgressReport.push_step')
    def test_event(self, fake_push):
        state = PT_MESSAGES.keys()[0]
        pr = ProgressReport()
        cb = ProcessTransCallback(pr)

        # test
        cb.event(state)

        # validation
        fake_push.assert_called_with(PT_MESSAGES[state])

    @patch('pulp_rpm.handlers.rpmtools.ProgressReport.push_step')
    def test_unknown_event(self, fake_push):
        state = '@#$%^&*'
        pr = ProgressReport()
        cb = ProcessTransCallback(pr)

        # test
        cb.event(state)

        # validation
        self.assertFalse(fake_push.called)


class TestReportIntegration(TestCase):

    def test_tx_event(self):
        pr = ProgressReport()
        pr._updated = Mock()
        cb = ProcessTransCallback(pr)
        for state in sorted(PT_MESSAGES.keys()):
            cb.event(state)
        pr.set_status(True)
        self.assertEqual(len(PT_MESSAGES), len(pr.steps))
        i = 0
        for state in sorted(PT_MESSAGES.keys()):
            step = pr.steps[i]
            name = PT_MESSAGES[state]
            self.assertEqual(step[0], name)
            self.assertTrue(step[1])
            i += 1

    def test_rpm_event(self):
        package = 'openssl'
        pr = Mock()
        cb = RPMCallback(pr)
        expected_actions = set()
        for action, description in cb.action.items():
            cb.event(package, action)
            cb.event(package, action)  # test 2nd (dup) ignored
            expected_actions.add((package, action))
            self.assertEqual(cb.events, expected_actions)
            pr.set_action.assert_called_with(description, package)

    def test_rpm_action(self):
        pr = ProgressReport()
        pr._updated = Mock()
        cb = RPMCallback(pr)
        for action in sorted(cb.action.keys()):
            package = '%s_package' % action
            cb.event(package, action)
            self.assertEqual(pr.details['action'], cb.action[action])
            self.assertEqual(pr.details['package'], package)
        self.assertEqual(len(pr.steps), 0)

    def test_rpm_filelog(self):
        pr = ProgressReport()
        pr._updated = Mock()
        cb = RPMCallback(pr)
        for action in sorted(cb.fileaction.keys()):
            package = '%s_package' % action
            cb.filelog(package, action)
            self.assertEqual(pr.details['action'], cb.fileaction[action])
            self.assertEqual(pr.details['package'], package)
        self.assertEqual(len(pr.steps), 0)

    def test_rpm_errorlog(self):
        pr = ProgressReport()
        pr._updated = Mock()
        cb = RPMCallback(pr)
        message = 'Something bad happened'
        cb.errorlog(message)
        self.assertEqual(pr.details['error'], message)
        self.assertEqual(len(pr.steps), 0)


class TestRPMCallback(TestCase):

    def test_event(self):
        package = 'openssl'
        pr = Mock()
        cb = RPMCallback(pr)
        expected_actions = set()
        for action, description in cb.action.items():
            cb.event(package, action)
            cb.event(package, action)  # test 2nd (dup) ignored
            expected_actions.add((package, action))
            self.assertEqual(cb.events, expected_actions)
            pr.set_action.assert_called_with(description, package)

    def test_filelog(self):
        pr = Mock()
        package = 'openssl'
        action = RPMCallback(pr).fileaction.keys()[0]
        cb = RPMCallback(pr)

        # test
        cb.filelog(package, action)

        # validation
        pr.set_action.assert_called_with(cb.fileaction[action], package)

    def test_unknown_filelog(self):
        pr = Mock()
        package = 'openssl'
        action = 123456
        cb = RPMCallback(pr)

        # test
        cb.filelog(package, action)

        # validation
        pr.set_action.assert_called_with(str(action), package)

    def test_verify_txmbr(self):
        pr = Mock()
        tx = Mock()
        tx.po = 'openssl'

        # test
        cb = RPMCallback(pr)
        cb.verify_txmbr(None, tx, 10)

        # validation
        pr.set_action.assert_called_with('Verifying', tx.po)


class TestDownloadCallback(TestCase):

    def test_construction(self):
        pr = Mock()
        cb = DownloadCallback(pr)

        # validation
        self.assertEqual(cb.report, pr)

    def test_doStart(self):
        pr = Mock()

        # test
        cb = DownloadCallback(pr)
        cb._getName = Mock(return_value='Testing')
        cb.totSize = '100'
        cb._do_start()

        # validation
        pr.set_action.assert_called_with('Downloading', 'Testing | 100')
