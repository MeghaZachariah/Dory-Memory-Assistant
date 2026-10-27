import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api.dart';
import 'calls.dart';
import 'home_screen.dart';
import 'settings.dart';
import 'theme.dart';

/// Sign in with the family's account. There is no sign-up here: the family makes the
/// account on the Dory website, and the same login is used on the person's phone.
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, this.message});

  /// Shown above the form, e.g. "Please sign in again" after a session ended.
  final String? message;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  DorySettings? _s;
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _server = TextEditingController();
  bool _showPassword = false;
  bool _showServer = false;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _error = widget.message;
    DorySettings.load().then((s) {
      if (!mounted) return;
      setState(() {
        _s = s;
        _email.text = s.accountEmail;
        _server.text = s.serverUrl;
      });
    });
  }

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _server.dispose();
    super.dispose();
  }

  Future<void> _signIn() async {
    final s = _s;
    if (s == null || _busy) return;
    if (_email.text.trim().isEmpty || _password.text.isEmpty) {
      setState(() => _error = 'Please enter the email and password.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    s.serverUrl = _server.text.trim().replaceAll(RegExp(r'/+$'), '');
    try {
      final (token, account) = await DoryApi(s).login(_email.text, _password.text);
      s
        ..sessionToken = token
        ..accountEmail = account['email'] as String? ?? _email.text.trim()
        ..personId = account['person_id'] as String
        ..personName = account['person_name'] as String? ?? '';
      await s.save();
      await scheduleDailyCalls(s);
      if (!mounted) return;
      Navigator.of(context).pushAndRemoveUntil(MaterialPageRoute(builder: (_) => const HomeScreen()), (_) => false);
    } on DoryApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: darkStatusBar,
      child: Scaffold(
        body: SafeArea(
          child: _s == null
              ? const Center(child: CircularProgressIndicator())
              : AutofillGroup(
                  child: ListView(
                    padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
                    children: [
                      Row(children: [
                        Container(
                          width: 38,
                          height: 38,
                          decoration: BoxDecoration(color: DoryColors.primary, borderRadius: BorderRadius.circular(11)),
                          child: const Icon(Icons.graphic_eq, color: Colors.white, size: 22),
                        ),
                        const SizedBox(width: 10),
                        Text('Dory', style: t.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
                      ]),
                      const SizedBox(height: 36),
                      Text('Sign in', style: t.displaySmall?.copyWith(fontWeight: FontWeight.w800)),
                      const SizedBox(height: 6),
                      Text('Use the account your family made on the Dory website.',
                          style: t.titleMedium?.copyWith(color: DoryColors.muted)),
                      const SizedBox(height: 24),
                      if (_error != null) ...[
                        Container(
                          padding: const EdgeInsets.all(14),
                          decoration: BoxDecoration(
                            color: DoryColors.warn.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(14),
                          ),
                          child: Text(_error!, style: t.bodyLarge?.copyWith(color: DoryColors.ink)),
                        ),
                        const SizedBox(height: 16),
                      ],
                      _Card(children: [
                        const _Label('Email'),
                        TextField(
                          controller: _email,
                          keyboardType: TextInputType.emailAddress,
                          autofillHints: const [AutofillHints.email, AutofillHints.username],
                          textInputAction: TextInputAction.next,
                          autocorrect: false,
                          style: t.titleMedium?.copyWith(fontWeight: FontWeight.w600),
                          decoration: _decoration('family@example.com'),
                        ),
                        const SizedBox(height: 16),
                        const _Label('Password'),
                        TextField(
                          controller: _password,
                          obscureText: !_showPassword,
                          autofillHints: const [AutofillHints.password],
                          textInputAction: TextInputAction.done,
                          onSubmitted: (_) => _signIn(),
                          style: t.titleMedium?.copyWith(fontWeight: FontWeight.w600),
                          decoration: _decoration('Password').copyWith(
                            suffixIcon: IconButton(
                              tooltip: _showPassword ? 'Hide password' : 'Show password',
                              icon: Icon(_showPassword ? Icons.visibility_off_outlined : Icons.visibility_outlined,
                                  color: DoryColors.muted),
                              onPressed: () => setState(() => _showPassword = !_showPassword),
                            ),
                          ),
                        ),
                      ]),
                      const SizedBox(height: 20),
                      SizedBox(
                        height: 58,
                        child: FilledButton(
                          onPressed: _busy ? null : _signIn,
                          style: FilledButton.styleFrom(
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18))),
                          child: _busy
                              ? const SizedBox(
                                  width: 24,
                                  height: 24,
                                  child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white))
                              : Text('Sign in',
                                  style: t.titleLarge?.copyWith(color: Colors.white, fontWeight: FontWeight.w700)),
                        ),
                      ),
                      const SizedBox(height: 28),
                      Text(
                        'No account yet? A family member can create one on the Dory website, '
                        'then sign in here with the same email and password.',
                        style: t.bodyMedium?.copyWith(color: DoryColors.muted),
                      ),
                      const SizedBox(height: 12),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: TextButton.icon(
                          onPressed: () => setState(() => _showServer = !_showServer),
                          icon: Icon(_showServer ? Icons.expand_less : Icons.expand_more),
                          label: const Text('Server address'),
                        ),
                      ),
                      if (_showServer)
                        _Card(children: [
                          const _Label('Dory server address'),
                          TextField(
                            controller: _server,
                            keyboardType: TextInputType.url,
                            autocorrect: false,
                            style: t.titleMedium?.copyWith(fontWeight: FontWeight.w600),
                            decoration: _decoration('https://dory.example.com'),
                          ),
                        ]),
                    ],
                  ),
                ),
        ),
      ),
    );
  }
}

/// Sign out on this phone: ends the session on the server, stops the daily calls and
/// goes back to the login screen. The email is kept to make signing in again easier.
Future<void> signOut(BuildContext context, {String? message}) async {
  final s = await DorySettings.load();
  await DoryApi(s).logout();
  s.sessionToken = '';
  await s.save();
  await scheduleDailyCalls(s); // cancels them: no calls while signed out
  if (!context.mounted) return;
  Navigator.of(context)
      .pushAndRemoveUntil(MaterialPageRoute(builder: (_) => LoginScreen(message: message)), (_) => false);
}

InputDecoration _decoration(String hint) => InputDecoration(
      hintText: hint,
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

class _Label extends StatelessWidget {
  const _Label(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(left: 2, bottom: 6),
        child: Text(text, style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: DoryColors.muted)),
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
