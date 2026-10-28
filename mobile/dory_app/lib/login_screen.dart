import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api.dart';
import 'calls.dart';
import 'home_screen.dart';
import 'settings.dart';
import 'theme.dart';

/// Sign in with the family's account, in the same style as the Dory website. There is no
/// sign-up here: the family makes the account on the website, and the same login is used
/// on the person's phone.
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
      setState(() => _error = 'Please enter the family account’s email and password.');
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
      if (!mounted) return;
      setState(() => _error = e.message.startsWith('Wrong email')
          ? 'We couldn’t sign you in. Check the family account details and try again.'
          : e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: lightStatusBar,
      child: Scaffold(
        backgroundColor: DoryColors.navy,
        body: Stack(children: [
          // The website's soft mint and blue glows behind everything.
          const Positioned(top: -120, right: -100, child: _Glow(color: Color(0x263DBD9D), size: 360)),
          const Positioned(bottom: -140, left: -120, child: _Glow(color: Color(0x38355B8A), size: 400)),
          SafeArea(
            child: _s == null
                ? const Center(child: CircularProgressIndicator(color: DoryColors.mint))
                : AutofillGroup(
                    child: ListView(
                      padding: const EdgeInsets.fromLTRB(22, 18, 22, 24),
                      children: [
                        const DoryLogo(),
                        const SizedBox(height: 40),
                        Container(
                          padding: const EdgeInsets.fromLTRB(22, 24, 22, 24),
                          decoration: BoxDecoration(
                            color: Colors.white.withValues(alpha: 0.07),
                            borderRadius: BorderRadius.circular(30),
                            border: Border.all(color: Colors.white.withValues(alpha: 0.15)),
                          ),
                          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                            Row(children: [
                              const Icon(Icons.auto_awesome, size: 15, color: DoryColors.mint),
                              const SizedBox(width: 8),
                              Text('FAMILY ACCOUNT', style: eyebrow(color: DoryColors.mint)),
                            ]),
                            const SizedBox(height: 14),
                            Text('Welcome back.', style: display(40, color: Colors.white)),
                            const SizedBox(height: 10),
                            Text('Sign in to continue caring with Dory.',
                                style: t.titleMedium?.copyWith(color: DoryColors.onDarkMuted)),
                            const SizedBox(height: 24),
                            if (_error != null) ...[
                              Container(
                                padding: const EdgeInsets.all(14),
                                decoration: BoxDecoration(
                                  color: const Color(0x33D86D62),
                                  borderRadius: BorderRadius.circular(16),
                                  border: Border.all(color: const Color(0x66EF9B8E)),
                                ),
                                child: Text(_error!, style: t.bodyLarge?.copyWith(color: const Color(0xFFFFDAD3))),
                              ),
                              const SizedBox(height: 18),
                            ],
                            const _Label('EMAIL'),
                            TextField(
                              controller: _email,
                              keyboardType: TextInputType.emailAddress,
                              autofillHints: const [AutofillHints.email, AutofillHints.username],
                              textInputAction: TextInputAction.next,
                              autocorrect: false,
                              style: _fieldText,
                              cursorColor: DoryColors.mint,
                              decoration: _decoration('family@example.com'),
                            ),
                            const SizedBox(height: 16),
                            const _Label('PASSWORD'),
                            TextField(
                              controller: _password,
                              obscureText: !_showPassword,
                              autofillHints: const [AutofillHints.password],
                              textInputAction: TextInputAction.done,
                              onSubmitted: (_) => _signIn(),
                              style: _fieldText,
                              cursorColor: DoryColors.mint,
                              decoration: _decoration('Password').copyWith(
                                suffixIcon: IconButton(
                                  tooltip: _showPassword ? 'Hide password' : 'Show password',
                                  icon: Icon(
                                    _showPassword ? Icons.visibility_off_outlined : Icons.visibility_outlined,
                                    color: DoryColors.onDarkMuted,
                                  ),
                                  onPressed: () => setState(() => _showPassword = !_showPassword),
                                ),
                              ),
                            ),
                            const SizedBox(height: 22),
                            SizedBox(
                              height: 58,
                              child: FilledButton(
                                onPressed: _busy ? null : _signIn,
                                style: FilledButton.styleFrom(
                                  backgroundColor: DoryColors.mint,
                                  foregroundColor: const Color(0xFF082131),
                                  disabledBackgroundColor: DoryColors.mint.withValues(alpha: 0.5),
                                ),
                                child: _busy
                                    ? const SizedBox(
                                        width: 24,
                                        height: 24,
                                        child: CircularProgressIndicator(strokeWidth: 2.5, color: Color(0xFF082131)),
                                      )
                                    : Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                                        Text('Sign in',
                                            style: t.titleLarge?.copyWith(
                                                color: const Color(0xFF082131), fontWeight: FontWeight.w700)),
                                        const SizedBox(width: 8),
                                        const Icon(Icons.arrow_forward_rounded, size: 20),
                                      ]),
                              ),
                            ),
                          ]),
                        ),
                        const SizedBox(height: 22),
                        Text(
                          'One account connects a person and the family who supports them. '
                          'New to Dory? A family member can create the account on the Dory website.',
                          style: t.bodyMedium?.copyWith(color: DoryColors.onDarkMuted, height: 1.5),
                        ),
                        const SizedBox(height: 8),
                        Align(
                          alignment: Alignment.centerLeft,
                          child: TextButton.icon(
                            onPressed: () => setState(() => _showServer = !_showServer),
                            style: TextButton.styleFrom(foregroundColor: DoryColors.mint),
                            icon: Icon(_showServer ? Icons.expand_less : Icons.expand_more),
                            label: const Text('Server address'),
                          ),
                        ),
                        if (_showServer) ...[
                          const _Label('DORY SERVER ADDRESS'),
                          TextField(
                            controller: _server,
                            keyboardType: TextInputType.url,
                            autocorrect: false,
                            style: _fieldText,
                            cursorColor: DoryColors.mint,
                            decoration: _decoration('https://dory.example.com'),
                          ),
                        ],
                        const SizedBox(height: 28),
                        Divider(color: Colors.white.withValues(alpha: 0.10)),
                        const SizedBox(height: 10),
                        Row(children: [
                          Text('Private by design', style: t.bodySmall?.copyWith(color: const Color(0xFF6F9297))),
                          const Spacer(),
                          const Icon(Icons.lock_outline_rounded, size: 14, color: Color(0xFF6F9297)),
                          const SizedBox(width: 5),
                          Text('Your family circle stays yours',
                              style: t.bodySmall?.copyWith(color: const Color(0xFF6F9297))),
                        ]),
                      ],
                    ),
                  ),
          ),
        ]),
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

const _fieldText = TextStyle(fontFamily: fontText, fontSize: 17, fontWeight: FontWeight.w600, color: Colors.white);

/// Translucent fields on navy, with a mint outline when focused (as on the website).
InputDecoration _decoration(String hint) => InputDecoration(
      hintText: hint,
      hintStyle: const TextStyle(color: Color(0xFF6F9297), fontWeight: FontWeight.w400),
      filled: true,
      fillColor: Colors.white.withValues(alpha: 0.07),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16), borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.10))),
      enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16), borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.10))),
      focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16), borderSide: const BorderSide(color: DoryColors.mint, width: 1.5)),
    );

class _Label extends StatelessWidget {
  const _Label(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(left: 2, bottom: 8),
        child: Text(text, style: eyebrow(color: const Color(0xFF8EAAAD)).copyWith(fontSize: 11, letterSpacing: 1.6)),
      );
}

class _Glow extends StatelessWidget {
  const _Glow({required this.color, required this.size});
  final Color color;
  final double size;

  @override
  Widget build(BuildContext context) => IgnorePointer(
        child: Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: RadialGradient(colors: [color, color.withValues(alpha: 0)]),
          ),
        ),
      );
}
