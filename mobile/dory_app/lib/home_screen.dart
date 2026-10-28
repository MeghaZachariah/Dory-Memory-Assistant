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
      value: lightStatusBar,
      child: Scaffold(
        body: CustomScrollView(
          slivers: [
            SliverToBoxAdapter(child: _Header(onSettings: _openSettings)),
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
              sliver: SliverList.list(children: [
                _Greeting(greeting: _greeting(), name: name, serverOk: _serverOk, onFix: _openSettings),
                const SizedBox(height: 16),
                _TalkCard(onPressed: () => _call(CallMode.ask)),
                const SizedBox(height: 14),
                IntrinsicHeight(
                  child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                    Expanded(
                      child: _ActionCard(
                        icon: Icons.nightlight_outlined,
                        title: 'Evening chat',
                        subtitle: 'A little help remembering the day.',
                        onPressed: () => _call(CallMode.evening),
                      ),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: _ActionCard(
                        icon: Icons.wb_sunny_outlined,
                        title: 'Morning briefing',
                        subtitle: 'Hear today’s plan, gently.',
                        onPressed: () => _call(CallMode.briefing),
                      ),
                    ),
                  ]),
                ),
              ]),
            ),
            SliverFillRemaining(
              hasScrollBody: false,
              child: SafeArea(
                top: false,
                minimum: const EdgeInsets.fromLTRB(20, 24, 20, 20),
                child: Column(mainAxisAlignment: MainAxisAlignment.end, children: [
                  Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                    const Icon(Icons.verified_user_outlined, size: 16, color: DoryColors.ok),
                    const SizedBox(width: 6),
                    Text('Dory promise: no source, no answer.', style: t.bodyMedium?.copyWith(color: DoryColors.muted)),
                  ]),
                  const SizedBox(height: 12),
                  _DailyCallsBar(settings: s, onTestRing: _testRing),
                ]),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// White rounded card with a thin outline, used for everything except the main button.
BoxDecoration _cardDecoration({double radius = 24}) => BoxDecoration(
      color: DoryColors.card,
      borderRadius: BorderRadius.circular(radius),
      border: Border.all(color: DoryColors.border),
    );

/// The navy band at the top, like the website's portal header.
class _Header extends StatelessWidget {
  const _Header({required this.onSettings});
  final VoidCallback onSettings;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: DoryColors.navy,
      child: SafeArea(
        bottom: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 14, 16, 18),
          child: Row(children: [
            const DoryLogo(),
            const Spacer(),
            Material(
              color: Colors.white.withValues(alpha: 0.06),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(14),
                side: BorderSide(color: Colors.white.withValues(alpha: 0.10)),
              ),
              child: IconButton(
                tooltip: 'Settings',
                icon: const Icon(Icons.settings_outlined, color: Color(0xFF9DB9BC)),
                onPressed: onSettings,
              ),
            ),
          ]),
        ),
      ),
    );
  }
}

class _Greeting extends StatelessWidget {
  const _Greeting({required this.greeting, required this.name, required this.serverOk, required this.onFix});
  final String greeting;
  final String name;
  final bool? serverOk;
  final VoidCallback onFix;

  static const _days = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY'];
  static const _months = [
    'JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', //
    'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER',
  ];

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 18),
      decoration: _cardDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('${_days[now.weekday - 1]}, ${_months[now.month - 1]} ${now.day}', style: eyebrow()),
        const SizedBox(height: 8),
        Text(name.isEmpty ? 'Your calm corner is ready.' : '$greeting, $name.', style: display(36)),
        const SizedBox(height: 14),
        _ServerStatus(ok: serverOk, onFix: onFix),
      ]),
    );
  }
}

class _ServerStatus extends StatelessWidget {
  const _ServerStatus({required this.ok, required this.onFix});
  final bool? ok;
  final VoidCallback onFix;

  @override
  Widget build(BuildContext context) {
    final style = Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700);
    final (label, dot, fg, bg) = switch (ok) {
      null => ('Connecting…', DoryColors.muted, DoryColors.muted, DoryColors.page),
      true => ('Dory is here', DoryColors.ok, const Color(0xFF4E9272), DoryColors.primarySoft),
      false => (
          'Memory book offline · Check settings',
          DoryColors.warn,
          const Color(0xFF8A5A14),
          const Color(0xFFFFF4D8),
        ),
    };
    return InkWell(
      borderRadius: BorderRadius.circular(20),
      onTap: ok == false ? onFix : null,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(20)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(Icons.circle, size: 9, color: dot),
          const SizedBox(width: 8),
          Flexible(child: Text(label, style: style?.copyWith(color: fg))),
        ]),
      ),
    );
  }
}

/// The main button, in the website's navy-and-mint card style.
class _TalkCard extends StatelessWidget {
  const _TalkCard({required this.onPressed});
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(28),
        boxShadow: [
          BoxShadow(color: DoryColors.deep.withValues(alpha: 0.18), blurRadius: 30, offset: const Offset(0, 14)),
        ],
      ),
      child: Material(
        color: DoryColors.deep,
        borderRadius: BorderRadius.circular(28),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onPressed,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 28),
            child: Row(children: [
              Container(
                width: 58,
                height: 58,
                decoration: BoxDecoration(color: DoryColors.mint.withValues(alpha: 0.15), shape: BoxShape.circle),
                child: const Icon(Icons.mic_none_rounded, color: DoryColors.mint, size: 30),
              ),
              const SizedBox(width: 18),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('Talk to Dory',
                      style: t.headlineSmall?.copyWith(color: Colors.white, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 4),
                  Text('Ready when you are', style: t.titleMedium?.copyWith(color: const Color(0xFFA4C0BD))),
                ]),
              ),
              const Icon(Icons.arrow_forward_rounded, color: DoryColors.mint),
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
        borderRadius: BorderRadius.circular(24),
        onTap: onPressed,
        child: Ink(
          decoration: _cardDecoration(),
          padding: const EdgeInsets.all(18),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Container(
              width: 46,
              height: 46,
              decoration: BoxDecoration(color: DoryColors.primarySoft, borderRadius: BorderRadius.circular(14)),
              child: Icon(icon, color: DoryColors.primary, size: 24),
            ),
            const SizedBox(height: 20),
            Text(title, style: t.titleLarge?.copyWith(fontWeight: FontWeight.w700, height: 1.2)),
            const SizedBox(height: 4),
            Text(subtitle, style: t.bodyLarge?.copyWith(color: DoryColors.muted, height: 1.35)),
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
      decoration: _cardDecoration(radius: 22),
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
            backgroundColor: DoryColors.primarySoft,
            side: BorderSide.none,
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            textStyle: t.titleSmall?.copyWith(fontWeight: FontWeight.w700),
          ),
        ),
      ]),
    );
  }
}
