import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api.dart';
import 'call_screen.dart';
import 'calls.dart';
import 'login_screen.dart';
import 'settings.dart';
import 'settings_screen.dart';
import 'theme.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  DorySettings? _settings;
  bool? _serverOk;

  @override
  void initState() {
    super.initState();
    _load(firstRun: true);
  }

  Future<void> _load({bool firstRun = false}) async {
    final s = await DorySettings.load();
    if (firstRun) {
      await requestCallPermissions();
      await scheduleDailyCalls(s);
    }
    final ok = await DoryApi(s).health();
    if (ok) {
      try {
        final account = await DoryApi(s).me(); // also picks up a renamed person
        s
          ..personId = account['person_id'] as String? ?? s.personId
          ..personName = account['person_name'] as String? ?? s.personName;
        await s.save();
      } on DoryAuthException {
        if (mounted) await signOut(context, message: 'You were signed out. Please sign in again.');
        return;
      } catch (_) {
        // Server trouble: keep going with what the phone already knows.
      }
    }
    if (!mounted) return;
    setState(() {
      _settings = s;
      _serverOk = ok;
    });
  }

  void _call(CallMode mode) {
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => CallScreen(mode: mode)));
  }

  Future<void> _testRing() async {
    await scheduleTestCall();
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
      content: Text('Dory will ring in 10 seconds. You can lock the phone now.', style: TextStyle(fontSize: 18)),
    ));
  }

  Future<void> _openSettings() async {
    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => const SettingsScreen()));
    _load();
  }

  String _greeting() {
    final h = DateTime.now().hour;
    return h < 12 ? 'Good morning' : (h < 17 ? 'Good afternoon' : 'Good evening');
  }

  @override
  Widget build(BuildContext context) {
    final s = _settings;
    final t = Theme.of(context).textTheme;
    final name = s?.personName ?? '';
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: darkStatusBar,
      child: Scaffold(
        body: SafeArea(
          child: CustomScrollView(
            slivers: [
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
                sliver: SliverList.list(children: [
                  _Header(onSettings: _openSettings),
                  const SizedBox(height: 28),
                  Text(name.isEmpty ? '${_greeting()}.' : '${_greeting()},',
                      style: t.titleLarge?.copyWith(color: DoryColors.primary, fontWeight: FontWeight.w500)),
                  if (name.isNotEmpty)
                    Text(name,
                        style: t.displayMedium?.copyWith(fontWeight: FontWeight.w800, letterSpacing: -1, height: 1.15)),
                  const SizedBox(height: 14),
                  Align(alignment: Alignment.centerLeft, child: _ServerStatus(ok: _serverOk, onFix: _openSettings)),
                  const SizedBox(height: 24),
                  _TalkCard(onPressed: () => _call(CallMode.ask)),
                  const SizedBox(height: 14),
                  IntrinsicHeight(
                    child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                      Expanded(
                        child: _ActionCard(
                          icon: Icons.nightlight_outlined,
                          title: 'Evening chat',
                          subtitle: 'Talk about your day',
                          onPressed: () => _call(CallMode.evening),
                        ),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: _ActionCard(
                          icon: Icons.wb_sunny_outlined,
                          title: 'Morning reminder',
                          subtitle: 'Plan the day ahead',
                          onPressed: () => _call(CallMode.briefing),
                        ),
                      ),
                    ]),
                  ),
                ]),
              ),
              SliverFillRemaining(
                hasScrollBody: false,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(20, 24, 20, 20),
                  child: Align(
                    alignment: Alignment.bottomCenter,
                    child: _DailyCallsBar(settings: s, onTestRing: _testRing),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// White rounded card with a thin outline, used for everything except the main button.
BoxDecoration _cardDecoration({double radius = 22}) => BoxDecoration(
      color: DoryColors.card,
      borderRadius: BorderRadius.circular(radius),
      border: Border.all(color: DoryColors.border),
    );

class _Header extends StatelessWidget {
  const _Header({required this.onSettings});
  final VoidCallback onSettings;

  @override
  Widget build(BuildContext context) {
    return Row(children: [
      Container(
        width: 38,
        height: 38,
        decoration: BoxDecoration(color: DoryColors.primary, borderRadius: BorderRadius.circular(11)),
        child: const Icon(Icons.graphic_eq, color: Colors.white, size: 22),
      ),
      const SizedBox(width: 10),
      Text('Dory', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
      const Spacer(),
      Material(
        color: DoryColors.card,
        shape: const CircleBorder(side: BorderSide(color: DoryColors.border)),
        child: IconButton(
          tooltip: 'Settings',
          icon: const Icon(Icons.settings_outlined, color: DoryColors.ink),
          onPressed: onSettings,
        ),
      ),
    ]);
  }
}

class _ServerStatus extends StatelessWidget {
  const _ServerStatus({required this.ok, required this.onFix});
  final bool? ok;
  final VoidCallback onFix;

  @override
  Widget build(BuildContext context) {
    final style = Theme.of(context).textTheme.titleSmall;
    final (label, color) = switch (ok) {
      null => ('Checking…', DoryColors.muted),
      true => ('Connected', DoryColors.ok),
      false => ('Offline', DoryColors.warn),
    };
    return InkWell(
      borderRadius: BorderRadius.circular(20),
      onTap: ok == false ? onFix : null,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: _cardDecoration(radius: 20),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(Icons.circle, size: 9, color: color),
          const SizedBox(width: 8),
          Text(label, style: style?.copyWith(color: DoryColors.ink)),
          if (ok == false) ...[
            Text('  ·  ', style: style?.copyWith(color: DoryColors.muted)),
            Text('Check settings', style: style?.copyWith(color: DoryColors.primary, fontWeight: FontWeight.w600)),
          ],
        ]),
      ),
    );
  }
}

class _TalkCard extends StatelessWidget {
  const _TalkCard({required this.onPressed});
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(26),
        boxShadow: [
          BoxShadow(color: DoryColors.primary.withValues(alpha: 0.28), blurRadius: 24, offset: const Offset(0, 10)),
        ],
      ),
      child: Material(
        color: DoryColors.primary,
        borderRadius: BorderRadius.circular(26),
        child: InkWell(
          borderRadius: BorderRadius.circular(26),
          onTap: onPressed,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 30),
            child: Row(children: [
              Container(
                width: 56,
                height: 56,
                decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.18), shape: BoxShape.circle),
                child: const Icon(Icons.mic_none_rounded, color: Colors.white, size: 30),
              ),
              const SizedBox(width: 18),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('Talk to Dory',
                      style: t.headlineSmall?.copyWith(color: Colors.white, fontWeight: FontWeight.w800)),
                  const SizedBox(height: 4),
                  Text('Tap and start speaking',
                      style: t.titleMedium?.copyWith(color: Colors.white.withValues(alpha: 0.85))),
                ]),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}

class _ActionCard extends StatelessWidget {
  const _ActionCard({required this.icon, required this.title, required this.subtitle, required this.onPressed});
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(22),
        onTap: onPressed,
        child: Ink(
          decoration: _cardDecoration(),
          padding: const EdgeInsets.all(18),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Container(
              width: 46,
              height: 46,
              decoration: BoxDecoration(color: DoryColors.primarySoft, borderRadius: BorderRadius.circular(13)),
              child: Icon(icon, color: DoryColors.primary, size: 24),
            ),
            const SizedBox(height: 22),
            Text(title, style: t.titleLarge?.copyWith(fontWeight: FontWeight.w700, height: 1.2)),
            const SizedBox(height: 4),
            Text(subtitle, style: t.bodyLarge?.copyWith(color: DoryColors.muted)),
          ]),
        ),
      ),
    );
  }
}

class _DailyCallsBar extends StatelessWidget {
  const _DailyCallsBar({required this.settings, required this.onTestRing});
  final DorySettings? settings;
  final VoidCallback onTestRing;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final s = settings;
    final on = s?.callsEnabled ?? false;
    final status = s == null
        ? ''
        : on
            ? '${s.morning.format(context)} · ${s.evening.format(context)}'
            : 'Switched off';
    return Container(
      padding: const EdgeInsets.fromLTRB(18, 14, 14, 14),
      decoration: _cardDecoration(radius: 20),
      child: Row(children: [
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
            Text('Daily calls', style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
            Text(status, style: t.bodyMedium?.copyWith(color: on ? DoryColors.ok : DoryColors.muted)),
          ]),
        ),
        OutlinedButton.icon(
          onPressed: onTestRing,
          icon: const Icon(Icons.notifications_none_rounded, size: 20),
          label: const Text('Test ring · 10s'),
          style: OutlinedButton.styleFrom(
            foregroundColor: DoryColors.primary,
            backgroundColor: DoryColors.primarySoft.withValues(alpha: 0.5),
            side: const BorderSide(color: DoryColors.primarySoft, width: 1.5),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            textStyle: t.titleSmall?.copyWith(fontWeight: FontWeight.w600),
          ),
        ),
      ]),
    );
  }
}
