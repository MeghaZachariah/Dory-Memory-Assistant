import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:dory_app/calls.dart';

void main() {
  test('call mode is read from the call extras', () {
    expect(callModeFrom('evening'), CallMode.evening);
    expect(callModeFrom('briefing'), CallMode.briefing);
    expect(callModeFrom(null), CallMode.ask);
  });

  test('next scheduled call is always in the future', () {
    final next = nextOccurrence(const TimeOfDay(hour: 0, minute: 0));
    expect(next.isAfter(DateTime.now()), isTrue);
  });
}
