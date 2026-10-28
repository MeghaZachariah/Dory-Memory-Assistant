import 'package:flutter/material.dart';

import 'api.dart';
import 'calls.dart';
import 'login_screen.dart';
import 'settings.dart';
import 'theme.dart';
import 'voice_setup_screen.dart';

/// Languages offered in the dropdown: speech-recognition locale -> label.
const _languages = {
  'en-IN': 'English (India)',
  'en-US': 'English (US)',
  'hi-IN': 'Hindi',
  'ml-IN': 'Malayalam',
  'ta-IN': 'Tamil',
};

/// Set up by a family member, not the person. Server address, name, language and call times.
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  DorySettings? _s;
  final _server = TextEditingController();
  final _token = TextEditingController();
  String _locale = 'en-IN';
  bool? _connected; // null while checking
  bool _testing = false;

  @override
  void initState() {
    super.initState();
    DorySettings.load().then((s) {
      if (!mounted) return;
      setState(() {
        _s = s;
        _server.text = s.serverUrl;
        _token.text = s.token;
        _locale = s.locale;
      });
      DoryApi(s).health().then((ok) {
        if (mounted) setState(() => _connected = ok);
      });
    });
  }

  DorySettings _current() {
    final s = _s!;
    s
      ..serverUrl = _server.text
      ..token = _token.text
      ..locale = _locale;
    return s;
  }

  Future<void> _save() async {
    final s = _current();
    await s.save();
    await scheduleDailyCalls(await DorySettings.load());
    if (mounted) Navigator.of(context).pop();
  }

  Future<void> _test() async {
    setState(() => _testing = true);
    final s = _current();
    await s.save();
    final ok = await DoryApi(await DorySettings.load()).health();
    if (!mounted) return;
    setState(() {
      _connected = ok;
      _testing = false;
    });
  }

  Future<void> _confirmSignOut(BuildContext context) async {
    final yes = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Sign out of Dory?'),
        content: const Text('Daily calls stop on this phone until someone signs in again.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(c, true), child: const Text('Sign out')),
        ],
      ),
    );
    if (yes == true && context.mounted) await signOut(context);
  }

  Future<void> _pickTime(bool evening) async {
    final s = _s!;
    final picked = await showTimePicker(context: context, initialTime: evening ? s.evening : s.morning);
    if (picked == null) return;
    setState(() {
      if (evening) {
        s.evening = picked;
      } else {
        s.morning = picked;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final s = _s;
    final t = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(
        leadingWidth: 64,
        leading: Padding(
          padding: const EdgeInsets.only(left: 16),
          child: Center(
            child: Material(
              color: DoryColors.card,
              shape: const CircleBorder(side: BorderSide(color: DoryColors.border)),
              child: IconButton(
                tooltip: 'Back',
                icon: const Icon(Icons.chevron_left_rounded, color: DoryColors.ink),
                onPressed: () => Navigator.of(context).maybePop(),
              ),
            ),
          ),
        ),
        title: Text('Settings', style: display(28)),
      ),
      body: s == null
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
              children: [
                const _SectionLabel('Connection'),
                _Card(children: [
                  _Field(
                    controller: _server,
                    label: 'Dory server address',
                    hint: 'http://192.168.1.20:8000',
                    type: TextInputType.url,
                  ),
                  const SizedBox(height: 12),
                  Row(children: [
                    _ConnectionStatus(connected: _connected),
                    const Spacer(),
                    _SoftButton(label: _testing ? 'Testing…' : 'Test connection', onPressed: _testing ? null : _test),
                  ]),
                ]),
                const _SectionLabel('Your family circle'),
                _Card(children: [
                  Row(children: [
                    Container(
                      width: 46,
                      height: 46,
                      decoration: BoxDecoration(color: DoryColors.primarySoft, borderRadius: BorderRadius.circular(13)),
                      child: const Icon(Icons.person_outline_rounded, color: DoryColors.primary),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(s.personName.isEmpty ? 'Signed in' : 'Caring for ${s.personName}',
                            style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                        Text(s.accountEmail, style: t.bodyMedium?.copyWith(color: DoryColors.muted)),
                      ]),
                    ),
                  ]),
                  const SizedBox(height: 12),
                  Text('The family can change names and family members on the Dory website.',
                      style: t.bodySmall?.copyWith(color: DoryColors.muted)),
                  const SizedBox(height: 8),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: TextButton.icon(
                      onPressed: () => _confirmSignOut(context),
                      style: TextButton.styleFrom(foregroundColor: DoryColors.hangUp),
                      icon: const Icon(Icons.logout_rounded),
                      label: const Text('Sign out'),
                    ),
                  ),
                ]),
                const _SectionLabel('Language'),
                _Card(children: [
                  _LanguagePicker(value: _locale, onChanged: (v) => setState(() => _locale = v)),
                ]),
                const _SectionLabel('Daily calls'),
                _Card(children: [
                  Row(children: [
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text('Daily calls', style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                        Text(
                          s.callsEnabled ? 'Dory rings at these times' : 'Switched off',
                          style: t.bodyMedium?.copyWith(color: s.callsEnabled ? DoryColors.ok : DoryColors.muted),
                        ),
                      ]),
                    ),
                    Switch(value: s.callsEnabled, onChanged: (v) => setState(() => s.callsEnabled = v)),
                  ]),
                  const Divider(height: 28, color: DoryColors.border),
                  _TimeRow(
                    icon: Icons.wb_sunny_outlined,
                    label: 'Morning reminder',
                    time: s.morning.format(context),
                    enabled: s.callsEnabled,
                    onTap: () => _pickTime(false),
                  ),
                  const SizedBox(height: 12),
                  _TimeRow(
                    icon: Icons.nightlight_outlined,
                    label: 'Evening chat',
                    time: s.evening.format(context),
                    enabled: s.callsEnabled,
                    onTap: () => _pickTime(true),
                  ),
                ]),
                const _SectionLabel('Family voice (optional)'),
                _Card(children: [
                  Row(children: [
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text('Speak in a family voice', style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                        Text(
                          s.useFamilyVoice ? 'On' : 'Off: Dory uses the phone voice',
                          style: t.bodyMedium?.copyWith(color: s.useFamilyVoice ? DoryColors.ok : DoryColors.muted),
                        ),
                      ]),
                    ),
                    _SoftButton(
                      label: 'Set up',
                      onPressed: () async {
                        await _current().save();
                        if (!context.mounted) return;
                        await Navigator.of(context).push(MaterialPageRoute(builder: (_) => const VoiceSetupScreen()));
                        final fresh = await DorySettings.load();
                        if (mounted) setState(() => s.useFamilyVoice = fresh.useFamilyVoice);
                      },
                    ),
                  ]),
                ]),
                const _SectionLabel('Advanced'),
                _Card(children: [
                  _Field(
                    controller: _token,
                    label: 'App token',
                    hint: 'Leave blank if not needed',
                    helper: 'Only needed if your server uses one',
                  ),
                ]),
              ],
            ),
      bottomNavigationBar: s == null
          ? null
          : SafeArea(
              minimum: const EdgeInsets.fromLTRB(20, 8, 20, 16),
              child: SizedBox(
                height: 58,
                child: FilledButton(
                  onPressed: _save,
                  style: FilledButton.styleFrom(shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18))),
                  child: Text('Save', style: t.titleLarge?.copyWith(color: Colors.white, fontWeight: FontWeight.w700)),
                ),
              ),
            ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(4, 20, 4, 8),
        child: Text(
          text.toUpperCase(),
          style: eyebrow().copyWith(fontSize: 11, letterSpacing: 1.8),
        ),
      );
}

class _Card extends StatelessWidget {
  const _Card({required this.children});
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: DoryColors.card,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: DoryColors.border),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
      );
}

InputDecoration _inputDecoration({String? hint, String? helper}) => InputDecoration(
      hintText: hint,
      helperText: helper,
      helperStyle: const TextStyle(color: DoryColors.muted),
      hintStyle: const TextStyle(color: DoryColors.muted, fontWeight: FontWeight.w400),
      filled: true,
      fillColor: DoryColors.page,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: DoryColors.border)),
      enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: DoryColors.border)),
      focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: DoryColors.primary, width: 1.5)),
    );

class _FieldLabel extends StatelessWidget {
  const _FieldLabel(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(left: 2, bottom: 6),
        child: Text(text, style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: DoryColors.muted)),
      );
}

class _Field extends StatelessWidget {
  const _Field({required this.controller, required this.label, this.hint, this.helper, this.type});
  final TextEditingController controller;
  final String label;
  final String? hint;
  final String? helper;
  final TextInputType? type;

  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        _FieldLabel(label),
        TextField(
          controller: controller,
          keyboardType: type,
          style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
          decoration: _inputDecoration(hint: hint, helper: helper),
        ),
      ]);
}

class _LanguagePicker extends StatelessWidget {
  const _LanguagePicker({required this.value, required this.onChanged});
  final String value;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    // Keep a language set some other way, even if it isn't in the list.
    final options = {..._languages, if (!_languages.containsKey(value)) value: value};
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const _FieldLabel('Language'),
      DropdownButtonFormField<String>(
        initialValue: value,
        isExpanded: true,
        decoration: _inputDecoration(),
        borderRadius: BorderRadius.circular(14),
        style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600, color: DoryColors.ink),
        items: [
          for (final e in options.entries)
            DropdownMenuItem(value: e.key, child: Text(e.key == e.value ? e.key : '${e.value} · ${e.key}')),
        ],
        onChanged: (v) {
          if (v != null) onChanged(v);
        },
      ),
    ]);
  }
}

class _ConnectionStatus extends StatelessWidget {
  const _ConnectionStatus({required this.connected});
  final bool? connected;

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (connected) {
      null => ('Checking…', DoryColors.muted),
      true => ('Connected', DoryColors.ok),
      false => ('Not connected', DoryColors.warn),
    };
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Icon(Icons.circle, size: 9, color: color),
      const SizedBox(width: 8),
      Text(label, style: Theme.of(context).textTheme.bodyLarge?.copyWith(color: DoryColors.ink)),
    ]);
  }
}

class _SoftButton extends StatelessWidget {
  const _SoftButton({required this.label, required this.onPressed});
  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) => TextButton(
        onPressed: onPressed,
        style: TextButton.styleFrom(
          foregroundColor: DoryColors.primary,
          backgroundColor: DoryColors.primarySoft,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(22)),
          textStyle: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
        ),
        child: Text(label),
      );
}

class _TimeRow extends StatelessWidget {
  const _TimeRow(
      {required this.icon, required this.label, required this.time, required this.enabled, required this.onTap});
  final IconData icon;
  final String label;
  final String time;
  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Opacity(
      opacity: enabled ? 1 : 0.5,
      child: Row(children: [
        Icon(icon, color: DoryColors.muted, size: 22),
        const SizedBox(width: 12),
        Expanded(child: Text(label, style: t.titleMedium)),
        InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: enabled ? onTap : null,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
            decoration: BoxDecoration(
              color: DoryColors.page,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: DoryColors.border),
            ),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Text(time, style: t.titleSmall?.copyWith(fontWeight: FontWeight.w600)),
              const SizedBox(width: 8),
              const Icon(Icons.schedule_rounded, size: 18, color: DoryColors.muted),
            ]),
          ),
        ),
      ]),
    );
  }
}
