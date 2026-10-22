import 'package:flutter/material.dart';

import 'api.dart';
import 'call_screen.dart';
import 'calls.dart';
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

  @override
  Widget build(BuildContext context) {
    final s = _settings;
    final t = Theme.of(context).textTheme;
    final hello = (s == null || s.personName.isEmpty) ? 'Hello' : 'Hello, ${s.personName}';
    return Scaffold(
      appBar: AppBar(
        title: Text('Dory', style: t.headlineMedium?.copyWith(fontWeight: FontWeight.w700)),
        actions: [
          IconButton(
            iconSize: 32,
            tooltip: 'Settings',
            icon: const Icon(Icons.settings),
            onPressed: () async {
              await Navigator.of(context).push(MaterialPageRoute(builder: (_) => const SettingsScreen()));
              _load();
            },
          ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            Text(hello, style: t.displaySmall),
            const SizedBox(height: 8),
            _ServerStatus(ok: _serverOk),
            const SizedBox(height: 28),
            _BigButton(
              icon: Icons.record_voice_over,
              label: 'Talk to Dory',
              color: DoryColors.answer,
              onPressed: () => _call(CallMode.ask),
            ),
            const SizedBox(height: 16),
            _BigButton(icon: Icons.nights_stay, label: 'Evening chat', onPressed: () => _call(CallMode.evening)),
            const SizedBox(height: 16),
            _BigButton(icon: Icons.wb_sunny, label: 'Morning reminder', onPressed: () => _call(CallMode.briefing)),
            const SizedBox(height: 28),
            if (s != null)
              Text(
                s.callsEnabled
                    ? 'Dory calls every day at ${s.morning.format(context)} and ${s.evening.format(context)}.'
                    : 'Daily calls are switched off.',
                style: t.titleMedium?.copyWith(color: DoryColors.mist),
              ),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: _testRing,
              icon: const Icon(Icons.ring_volume),
              label: const Text('Test the ring (10 seconds)', style: TextStyle(fontSize: 18)),
              style: OutlinedButton.styleFrom(
                foregroundColor: DoryColors.mist,
                padding: const EdgeInsets.symmetric(vertical: 16),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BigButton extends StatelessWidget {
  const _BigButton({required this.icon, required this.label, required this.onPressed, this.color = DoryColors.deep});
  final IconData icon;
  final String label;
  final VoidCallback onPressed;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 96,
      child: FilledButton.icon(
        style: FilledButton.styleFrom(
          backgroundColor: color,
          foregroundColor: DoryColors.cream,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
          alignment: Alignment.centerLeft,
          padding: const EdgeInsets.symmetric(horizontal: 24),
        ),
        onPressed: onPressed,
        icon: Icon(icon, size: 40),
        label: Text(label, style: Theme.of(context).textTheme.headlineSmall?.copyWith(color: DoryColors.cream)),
      ),
    );
  }
}

class _ServerStatus extends StatelessWidget {
  const _ServerStatus({required this.ok});
  final bool? ok;

  @override
  Widget build(BuildContext context) {
    final (text, color) = switch (ok) {
      null => ('Checking connection…', DoryColors.mist),
      true => ('Connected', const Color(0xFF81C784)),
      false => ('Can\'t reach the Dory server. Check Settings.', DoryColors.sun),
    };
    return Row(children: [
      Icon(Icons.circle, size: 14, color: color),
      const SizedBox(width: 8),
      Expanded(child: Text(text, style: Theme.of(context).textTheme.titleMedium?.copyWith(color: color))),
    ]);
  }
}
