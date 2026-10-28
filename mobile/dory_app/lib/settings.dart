import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Everything the app remembers on the phone. Edited on the Settings screen.
class DorySettings {
  DorySettings({
    required this.serverUrl,
    required this.personId,
    required this.personName,
    required this.token,
    required this.locale,
    required this.evening,
    required this.morning,
    required this.callsEnabled,
    required this.useFamilyVoice,
    required this.sessionToken,
    required this.accountEmail,
  });

  /// e.g. http://192.168.1.20:8000 (your laptop on the same Wi-Fi) or the hosted https URL.
  String serverUrl;
  String personId;
  String personName;

  /// Must match DORY_APP_TOKEN on the server, if one is set. Leave empty otherwise.
  String token;

  /// Language for listening and speaking, e.g. en-IN, hi-IN, ml-IN, ta-IN.
  String locale;
  TimeOfDay evening;
  TimeOfDay morning;
  bool callsEnabled;

  /// Speak in the recorded family voice (Settings → Family voice). Falls back to the phone voice.
  bool useFamilyVoice;

  /// Set by signing in (the family's account). Sent as "Authorization: Bearer ...".
  String sessionToken;
  String accountEmail;
  bool get signedIn => sessionToken.isNotEmpty;

  static Future<DorySettings> load() async {
    final p = await SharedPreferences.getInstance();
    return DorySettings(
      serverUrl: p.getString('serverUrl') ?? 'https://129-225-92-241.sslip.io/api',
      personId: p.getString('personId') ?? 'mary',
      personName: p.getString('personName') ?? 'Mary',
      token: p.getString('token') ?? '',
      locale: p.getString('locale') ?? 'en-IN',
      evening: TimeOfDay(hour: p.getInt('eveningHour') ?? 20, minute: p.getInt('eveningMinute') ?? 0),
      morning: TimeOfDay(hour: p.getInt('morningHour') ?? 8, minute: p.getInt('morningMinute') ?? 0),
      callsEnabled: p.getBool('callsEnabled') ?? true,
      useFamilyVoice: p.getBool('useFamilyVoice') ?? false,
      sessionToken: p.getString('sessionToken') ?? '',
      accountEmail: p.getString('accountEmail') ?? '',
    );
  }

  Future<void> save() async {
    final p = await SharedPreferences.getInstance();
    await p.setString('serverUrl', serverUrl.trim().replaceAll(RegExp(r'/+$'), ''));
    await p.setString('personId', personId.trim());
    await p.setString('personName', personName.trim());
    await p.setString('token', token.trim());
    await p.setString('locale', locale.trim());
    await p.setInt('eveningHour', evening.hour);
    await p.setInt('eveningMinute', evening.minute);
    await p.setInt('morningHour', morning.hour);
    await p.setInt('morningMinute', morning.minute);
    await p.setBool('callsEnabled', callsEnabled);
    await p.setBool('useFamilyVoice', useFamilyVoice);
    await p.setString('sessionToken', sessionToken);
    await p.setString('accountEmail', accountEmail);
  }
}
