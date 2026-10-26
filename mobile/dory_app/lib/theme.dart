import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Light, calm colours: a pale blue page, white cards and one strong blue.
/// Large type everywhere for older eyes.
class DoryColors {
  static const page = Color(0xFFF4F7FD); // background
  static const card = Color(0xFFFFFFFF); // cards, chips
  static const border = Color(0xFFE3E8F2); // card outlines
  static const ink = Color(0xFF0F1B3D); // main text
  static const muted = Color(0xFF6B7A99); // secondary text
  static const primary = Color(0xFF2347E0); // Talk to Dory, links, highlights
  static const primarySoft = Color(0xFFE8EEFE); // icon tiles, soft buttons
  static const ok = Color(0xFF1F9D63); // connected, calls on
  static const warn = Color(0xFFF08C2B); // offline
  static const hangUp = Color(0xFFD93636); // red: end call
}

/// Dark status-bar icons, for screens without an app bar.
const darkStatusBar = SystemUiOverlayStyle(
  statusBarColor: Colors.transparent,
  statusBarIconBrightness: Brightness.dark,
  statusBarBrightness: Brightness.light,
);

ThemeData doryTheme() {
  final base = ThemeData(
    useMaterial3: true,
    colorScheme: ColorScheme.fromSeed(seedColor: DoryColors.primary).copyWith(
      primary: DoryColors.primary,
      onPrimary: Colors.white,
      surface: DoryColors.page,
      onSurface: DoryColors.ink,
      outline: DoryColors.border,
    ),
    scaffoldBackgroundColor: DoryColors.page,
  );
  return base.copyWith(
    textTheme: base.textTheme.apply(bodyColor: DoryColors.ink, displayColor: DoryColors.ink),
    appBarTheme: const AppBarTheme(
      backgroundColor: DoryColors.page,
      foregroundColor: DoryColors.ink,
      elevation: 0,
      scrolledUnderElevation: 0,
      systemOverlayStyle: darkStatusBar,
    ),
    inputDecorationTheme: const InputDecorationTheme(filled: true, fillColor: DoryColors.card),
  );
}
