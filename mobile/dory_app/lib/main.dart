import 'dart:async';

import 'package:android_alarm_manager_plus/android_alarm_manager_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter_callkit_incoming/entities/entities.dart';
import 'package:flutter_callkit_incoming/flutter_callkit_incoming.dart';

import 'call_screen.dart';
import 'calls.dart';
import 'home_screen.dart';
import 'theme.dart';

final navigatorKey = GlobalKey<NavigatorState>();

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AndroidAlarmManager.initialize();
  runApp(const DoryApp());
}

class DoryApp extends StatefulWidget {
  const DoryApp({super.key});

  @override
  State<DoryApp> createState() => _DoryAppState();
}

class _DoryAppState extends State<DoryApp> {
  StreamSubscription<CallEvent?>? _events;
  final Set<String> _openedCalls = {};

  @override
  void initState() {
    super.initState();
    // The person pressed "Answer" while the app was running.
    _events = FlutterCallkitIncoming.onEvent.listen((event) {
      if (event is CallEventActionCallAccept) _openCall(event.callKitParams);
      // "Call back" pressed on a missed-call notification: let them talk to Dory.
      if (event is CallEventActionCallCallback) {
        navigatorKey.currentState?.push(MaterialPageRoute(builder: (_) => const CallScreen(mode: CallMode.ask)));
      }
    });
    // The person pressed "Answer" while the app was closed: Android starts the app, then we check.
    WidgetsBinding.instance.addPostFrameCallback((_) => _openAcceptedCallOnLaunch());
  }

  Future<void> _openAcceptedCallOnLaunch() async {
    final calls = await FlutterCallkitIncoming.activeCalls();
    for (final c in calls) {
      if (c.isAccepted) _openCall(c);
    }
  }

  void _openCall(CallKitParams params) {
    if (!_openedCalls.add(params.id)) return; // already open
    final mode = callModeFrom(params.extra?['mode']);
    navigatorKey.currentState?.push(MaterialPageRoute(builder: (_) => CallScreen(mode: mode, callId: params.id)));
  }

  @override
  void dispose() {
    _events?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Dory',
      navigatorKey: navigatorKey,
      debugShowCheckedModeBanner: false,
      theme: doryTheme(),
      // Text a little larger than the phone's setting, for older eyes.
      builder: (context, child) {
        final mq = MediaQuery.of(context);
        return MediaQuery(
          data: mq.copyWith(textScaler: TextScaler.linear((mq.textScaler.scale(16) / 16) * 1.15)),
          child: child!,
        );
      },
      home: const HomeScreen(),
    );
  }
}
