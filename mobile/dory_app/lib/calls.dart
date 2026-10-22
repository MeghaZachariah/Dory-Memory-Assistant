import 'dart:math';
import 'dart:ui';

import 'package:android_alarm_manager_plus/android_alarm_manager_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter_callkit_incoming/entities/entities.dart';
import 'package:flutter_callkit_incoming/flutter_callkit_incoming.dart';

import 'settings.dart';

/// What a call is for. Stored in the call's `extra` so the app knows what to do on "Answer".
enum CallMode { evening, briefing, ask }

CallMode callModeFrom(Object? value) =>
    CallMode.values.firstWhere((m) => m.name == value, orElse: () => CallMode.ask);

const int eveningAlarmId = 101;
const int morningAlarmId = 102;
const int testAlarmId = 199;

// --- Alarm callbacks. They run in the background, even when the app is closed. ---

@pragma('vm:entry-point')
Future<void> eveningAlarmCallback() async {
  DartPluginRegistrant.ensureInitialized();
  await showDoryCall(CallMode.evening);
}

@pragma('vm:entry-point')
Future<void> morningAlarmCallback() async {
  DartPluginRegistrant.ensureInitialized();
  await showDoryCall(CallMode.briefing);
}

/// Shows the full-screen "Dory is calling" screen with ringtone.
Future<void> showDoryCall(CallMode mode) async {
  final subtitle = switch (mode) {
    CallMode.evening => 'Evening chat',
    CallMode.briefing => 'Good morning',
    CallMode.ask => 'Calling',
  };
  final params = CallKitParams(
    id: _uuid(),
    nameCaller: 'Dory',
    appName: 'Dory',
    handle: subtitle,
    type: 0, // audio call
    duration: 60000, // ring for 60 seconds
    extra: <String, dynamic>{'mode': mode.name},
    missedCallNotification: const NotificationParams(
      showNotification: true,
      isShowCallback: true,
      subtitle: 'Missed call from Dory',
      callbackText: 'Call back',
    ),
    android: const AndroidParams(
      isCustomNotification: true,
      isShowLogo: false,
      ringtonePath: 'system_ringtone_default',
      backgroundColor: '#12324A',
      actionColor: '#2E7D32',
      textColor: '#FFFFFF',
      incomingCallNotificationChannelName: 'Dory calls',
      missedCallNotificationChannelName: 'Missed Dory calls',
      isShowFullLockedScreen: true,
      isShowCallID: false,
      textAccept: 'Answer',
      textDecline: 'Not now',
    ),
  );
  await FlutterCallkitIncoming.showCallkitIncoming(params);
}

/// Sets (or clears) the daily evening and morning calls from the settings.
Future<void> scheduleDailyCalls(DorySettings s) async {
  await AndroidAlarmManager.cancel(eveningAlarmId);
  await AndroidAlarmManager.cancel(morningAlarmId);
  if (!s.callsEnabled) return;
  await AndroidAlarmManager.periodic(
    const Duration(days: 1),
    eveningAlarmId,
    eveningAlarmCallback,
    startAt: nextOccurrence(s.evening),
    exact: true,
    wakeup: true,
    allowWhileIdle: true,
    rescheduleOnReboot: true,
  );
  await AndroidAlarmManager.periodic(
    const Duration(days: 1),
    morningAlarmId,
    morningAlarmCallback,
    startAt: nextOccurrence(s.morning),
    exact: true,
    wakeup: true,
    allowWhileIdle: true,
    rescheduleOnReboot: true,
  );
}

/// For the demo: ring in [delay], so you can lock the phone and watch it ring.
Future<void> scheduleTestCall({Duration delay = const Duration(seconds: 10)}) async {
  await AndroidAlarmManager.oneShot(delay, testAlarmId, eveningAlarmCallback,
      exact: true, wakeup: true, allowWhileIdle: true);
}

DateTime nextOccurrence(TimeOfDay t) {
  final now = DateTime.now();
  var at = DateTime(now.year, now.month, now.day, t.hour, t.minute);
  if (!at.isAfter(now)) at = at.add(const Duration(days: 1));
  return at;
}

/// Asks once for the permissions a ringing call needs (Android 13+ notifications, 14+ full screen).
Future<void> requestCallPermissions() async {
  await FlutterCallkitIncoming.requestNotificationPermission({
    'title': 'Allow Dory to call',
    'rationaleMessagePermission': 'Dory needs notifications to ring like a phone call.',
    'postNotificationMessageRequired': 'Please allow notifications for Dory in Settings.',
  });
  if (!await FlutterCallkitIncoming.canUseFullScreenIntent()) {
    await FlutterCallkitIncoming.requestFullIntentPermission();
  }
}

String _uuid() {
  final r = Random.secure();
  final b = List<int>.generate(16, (_) => r.nextInt(256));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  final h = b.map((x) => x.toRadixString(16).padLeft(2, '0')).join();
  return '${h.substring(0, 8)}-${h.substring(8, 12)}-${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
}
