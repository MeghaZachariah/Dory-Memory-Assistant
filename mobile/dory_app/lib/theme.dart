import 'package:flutter/material.dart';

/// Calm, high-contrast colours. Large type everywhere for older eyes.
class DoryColors {
  static const night = Color(0xFF0E2A3D); // background
  static const deep = Color(0xFF1C4560); // cards, chips
  static const cream = Color(0xFFFFF8EC); // main text
  static const mist = Color(0xFFB9CCD9); // secondary text
  static const sun = Color(0xFFFFC857); // highlight: listening, what you said
  static const answer = Color(0xFF2E7D32); // green: call buttons
  static const hangUp = Color(0xFFC62828); // red: end call
}

ThemeData doryTheme() {
  final base = ThemeData(
    useMaterial3: true,
    colorScheme: ColorScheme.fromSeed(seedColor: DoryColors.deep, brightness: Brightness.dark).copyWith(
      surface: DoryColors.night,
      primary: DoryColors.sun,
      onPrimary: DoryColors.night,
    ),
    scaffoldBackgroundColor: DoryColors.night,
  );
  return base.copyWith(
    textTheme: base.textTheme.apply(bodyColor: DoryColors.cream, displayColor: DoryColors.cream),
    appBarTheme: const AppBarTheme(backgroundColor: DoryColors.night, foregroundColor: DoryColors.cream),
  );
}
