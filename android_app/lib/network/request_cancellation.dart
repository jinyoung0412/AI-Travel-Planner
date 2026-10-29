import 'dart:async';

/// One screen operation; late responses never become a new recommendation.
class RequestCancellation {
  final _abort = Completer<void>();
  bool get isCancelled => _abort.isCompleted;
  Future<void> get signal => _abort.future;
  void cancel() {
    if (!_abort.isCompleted) _abort.complete();
  }
}
