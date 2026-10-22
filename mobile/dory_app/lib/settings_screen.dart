import 'package:flutter/material.dart';

import 'api.dart';
import 'calls.dart';
import 'settings.dart';
import 'theme.dart';

/// Set up by a family member, not the person. Server address, name, language and call times.
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  DorySettings? _s;
  final _server = TextEditingController();
  final _personId = TextEditingController();
  final _name = TextEditingController();
  final _token = TextEditingController();
  final _locale = TextEditingController();
  String? _testResult;

  @override
  void initState() {
    super.initState();
    DorySettings.load().then((s) {
      if (!mounted) return;
      setState(() {
        _s = s;
        _server.text = s.serverUrl;
        _personId.text = s.personId;
        _name.text = s.personName;
        _token.text = s.token;
        _locale.text = s.locale;
      });
    });
  }

  DorySettings _current() {
    final s = _s!;
    s
      ..serverUrl = _server.text
      ..personId = _personId.text
      ..personName = _name.text
      ..token = _token.text
      ..locale = _locale.text;
    return s;
  }

  Future<void> _save() async {
    final s = _current();
    await s.save();
    await scheduleDailyCalls(await DorySettings.load());
    if (mounted) Navigator.of(context).pop();
  }

  Future<void> _test() async {
    final s = _current();
    await s.save();
    final ok = await DoryApi(await DorySettings.load()).health();
    if (!mounted) return;
    setState(() => _testResult = ok ? 'Connected to the Dory server.' : 'Could not connect. Check the address and Wi-Fi.');
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

  Widget _field(TextEditingController c, String label, String hint, {TextInputType? type}) => Padding(
        padding: const EdgeInsets.only(bottom: 16),
        child: TextField(
          controller: c,
          keyboardType: type,
          style: const TextStyle(fontSize: 20),
          decoration: InputDecoration(labelText: label, hintText: hint, border: const OutlineInputBorder()),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final s = _s;
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: s == null
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(20),
              children: [
                _field(_server, 'Dory server address', 'http://192.168.1.20:8000', type: TextInputType.url),
                Row(children: [
                  OutlinedButton(onPressed: _test, child: const Text('Test connection')),
                  const SizedBox(width: 12),
                  if (_testResult != null) Expanded(child: Text(_testResult!, style: const TextStyle(color: DoryColors.mist))),
                ]),
                const SizedBox(height: 20),
                _field(_name, 'Their name', 'Mary'),
                _field(_personId, 'Person ID (from the family dashboard)', 'mary'),
                _field(_locale, 'Language', 'en-IN, hi-IN, ml-IN, ta-IN'),
                _field(_token, 'App token (only if the server uses one)', ''),
                SwitchListTile(
                  title: const Text('Daily calls', style: TextStyle(fontSize: 20)),
                  value: s.callsEnabled,
                  onChanged: (v) => setState(() => s.callsEnabled = v),
                ),
                ListTile(
                  title: const Text('Morning reminder', style: TextStyle(fontSize: 20)),
                  trailing: Text(s.morning.format(context), style: const TextStyle(fontSize: 20)),
                  onTap: () => _pickTime(false),
                ),
                ListTile(
                  title: const Text('Evening chat', style: TextStyle(fontSize: 20)),
                  trailing: Text(s.evening.format(context), style: const TextStyle(fontSize: 20)),
                  onTap: () => _pickTime(true),
                ),
                const SizedBox(height: 24),
                SizedBox(
                  height: 60,
                  child: FilledButton(onPressed: _save, child: const Text('Save', style: TextStyle(fontSize: 20))),
                ),
              ],
            ),
    );
  }
}
