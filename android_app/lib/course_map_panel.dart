import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:webview_flutter/webview_flutter.dart';

import 'course_map_data.dart';
import 'course_map_document.dart';
import 'network/course_route_client.dart';
import 'network/request_cancellation.dart';

abstract interface class CourseMapSession {
  Future<void> load(String html, String origin);
  Future<void> update(String script);
  Widget buildView();
  Future<void> close();
}

typedef CourseMapSessionFactory =
    CourseMapSession Function(
      ValueChanged<String> onMessage,
      VoidCallback onFailure,
    );

class CourseMapPanel extends StatefulWidget {
  final List<Map<String, dynamic>> places;
  final int? selectedIndex;
  final ValueChanged<int> onSelect;
  final KakaoMapConfiguration configuration;
  final CourseMapSessionFactory? sessionFactory;
  final Duration loadTimeout;
  final bool active;
  final String transport;
  final CourseRouteLoader? routeLoader;
  final Duration routeTimeout;

  const CourseMapPanel({
    super.key,
    required this.places,
    required this.selectedIndex,
    required this.onSelect,
    this.configuration = const KakaoMapConfiguration(),
    this.sessionFactory,
    this.loadTimeout = const Duration(seconds: 15),
    this.active = true,
    this.transport = '대중교통',
    this.routeLoader,
    this.routeTimeout = const Duration(seconds: 20),
  });

  @override
  State<CourseMapPanel> createState() => _CourseMapPanelState();
}

class _CourseMapPanelState extends State<CourseMapPanel> {
  CourseMapSession? _session;
  Timer? _timer;
  int _load = 0;
  int _revision = 0;
  bool _ready = false;
  bool _failed = false;
  bool _documentLoaded = false;
  bool _firstViewportRequested = false;
  String _stopsSignature = '';
  final CourseRouteClient _routeClient = CourseRouteClient();
  RequestCancellation? _routeCancellation;
  CourseRouteData? _route;
  bool _routeLoading = false;
  int _routeGeneration = 0;

  List<CourseMapStop> get _stops => courseMapStops(widget.places);
  bool get _supported =>
      widget.sessionFactory != null ||
      (!kIsWeb && WebViewPlatform.instance != null);
  bool get _available =>
      widget.configuration.isConfigured && _supported && _stops.isNotEmpty;
  bool get _enabled => widget.active && _available;

  Map<String, dynamic> get _payload => courseMapPayload(
    stops: _stops,
    selectedIndex: widget.selectedIndex,
    revision: _revision,
    route: _route,
  );

  @override
  void initState() {
    super.initState();
    _start();
    _startRoute();
  }

  @override
  void didUpdateWidget(CourseMapPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    final signature = jsonEncode(_stops.map((stop) => stop.toJson()).toList());
    final routeChanged =
        signature != _stopsSignature ||
        oldWidget.active != widget.active ||
        oldWidget.transport != widget.transport ||
        oldWidget.routeLoader != widget.routeLoader ||
        oldWidget.sessionFactory != widget.sessionFactory ||
        oldWidget.configuration.isConfigured !=
            widget.configuration.isConfigured;
    // Clear old geometry before any replacement document/update can capture
    // the new stops. The request generation also fences its late completion.
    if (routeChanged) {
      _cancelRoute();
      _route = null;
    }
    if (oldWidget.configuration.javascriptKey !=
            widget.configuration.javascriptKey ||
        oldWidget.configuration.origin != widget.configuration.origin ||
        oldWidget.sessionFactory != widget.sessionFactory ||
        (_enabled && _session == null) ||
        (!_enabled && _session != null)) {
      _start();
    } else if (_enabled &&
        (signature != _stopsSignature ||
            oldWidget.selectedIndex != widget.selectedIndex)) {
      _revision++;
      _stopsSignature = signature;
      if (_documentLoaded) unawaited(_update(_load));
    }
    if (routeChanged) _startRoute();
  }

  void _cancelRoute() {
    _routeGeneration++;
    _routeCancellation?.cancel();
    _routeCancellation = null;
    _routeLoading = false;
  }

  void _startRoute() {
    _cancelRoute();
    _route = null;
    _revision++;
    if (_documentLoaded && _enabled) unawaited(_update(_load));
    final stops = _stops;
    if (!_enabled ||
        _failed ||
        stops.length > 5 ||
        !stops.any((a) => stops.any((b) => b.index == a.index + 1))) {
      return;
    }
    final cancellation = RequestCancellation();
    _routeCancellation = cancellation;
    _routeLoading = true;
    final generation = _routeGeneration;
    final mode = courseRouteMode(widget.transport);
    unawaited(_loadRoute(generation, mode, stops, cancellation));
  }

  Future<void> _loadRoute(
    int generation,
    String mode,
    List<CourseMapStop> stops,
    RequestCancellation cancellation,
  ) async {
    CourseRouteData route;
    try {
      route =
          await Future.any<CourseRouteData>([
            (widget.routeLoader ?? _routeClient.load)(
              mode: mode,
              stops: stops,
              cancellation: cancellation,
            ),
            cancellation.signal.then((_) => CourseRouteData.unavailable(mode)),
          ]).timeout(
            widget.routeTimeout,
            onTimeout: () {
              cancellation.cancel();
              return CourseRouteData.unavailable(mode, 'timeout');
            },
          );
    } catch (_) {
      route = CourseRouteData.unavailable(mode);
    }
    if (!mounted || generation != _routeGeneration || !_enabled) return;
    setState(() {
      _routeLoading = false;
      _route = route;
      _revision++;
    });
    if (_documentLoaded) unawaited(_update(_load));
  }

  void _start() {
    _load++;
    _revision++;
    _timer?.cancel();
    final previous = _session;
    _session = null;
    if (previous != null) unawaited(previous.close());
    _ready = false;
    _failed = false;
    _documentLoaded = false;
    _firstViewportRequested = false;
    _stopsSignature = jsonEncode(_stops.map((stop) => stop.toJson()).toList());
    if (!_enabled) return;
    final load = _load;
    try {
      _session = (widget.sessionFactory ?? _WebViewMapSession.new)(
        (message) => _onMessage(load, message),
        () => _fail(load),
      );
      _timer = Timer(widget.loadTimeout, () => _fail(load));
      unawaited(_loadDocument(load));
    } catch (_) {
      _failed = true;
    }
  }

  Future<void> _loadDocument(int load) async {
    final session = _session;
    try {
      await session!.load(
        courseMapDocument(
          javascriptKey: widget.configuration.javascriptKey.trim(),
          payload: _payload,
        ),
        widget.configuration.origin,
      );
      if (!mounted || load != _load || _failed) return;
    } catch (_) {
      _fail(load);
    }
  }

  Future<void> _update(int load) async {
    try {
      await _session?.update(courseMapUpdateScript(_payload));
    } catch (_) {
      _fail(load);
    }
  }

  void _reconcileFirstViewport(int load) {
    if (_firstViewportRequested) return;
    _firstViewportRequested = true;
    // A platform WebView can finish its SDK tiles while still covered by the
    // Flutter loading layer. Re-read its viewport once that layer is painted out.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || load != _load || !_ready || _failed) return;
      unawaited(_sendFirstViewport(load));
    });
  }

  Future<void> _sendFirstViewport(int load) async {
    try {
      await _session?.update(
        'window.courseMap && window.courseMap.reconcileViewport();',
      );
    } catch (_) {
      _fail(load);
    }
  }

  void _onMessage(int load, String message) {
    if (!mounted || load != _load || _failed) return;
    try {
      final event = jsonDecode(message);
      if (event is! Map) return;
      if (event['type'] == 'document') {
        _documentLoaded = true;
        unawaited(_update(load));
        return;
      }
      if (event['revision'] != _revision) return;
      switch (event['type']) {
        case 'ready':
          _timer?.cancel();
          if (!_ready) {
            setState(() => _ready = true);
            _reconcileFirstViewport(load);
          }
        case 'error':
          _fail(load);
        case 'select':
          final index = event['index'];
          if (index is int && _stops.any((stop) => stop.index == index)) {
            widget.onSelect(index);
          }
      }
    } catch (_) {
      // The bridge accepts only the small typed events above, never raw errors.
    }
  }

  void _fail(int load) {
    if (!mounted || load != _load || _failed) return;
    _timer?.cancel();
    _cancelRoute();
    final session = _session;
    if (session != null) unawaited(session.close());
    setState(() {
      _failed = true;
      _ready = false;
    });
  }

  @override
  void dispose() {
    _load++;
    _timer?.cancel();
    _cancelRoute();
    _routeClient.close();
    final session = _session;
    if (session != null) unawaited(session.close());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!_available) return const SizedBox.shrink();
    final mapHeight = (MediaQuery.sizeOf(context).width * 678 / 968).clamp(
      240.0,
      320.0,
    );
    // Preserve the neighboring page's layout without keeping its WebView alive.
    if (!widget.active) {
      return Padding(
        padding: const EdgeInsets.only(top: 12),
        child: SizedBox(height: mapHeight, width: double.infinity),
      );
    }
    if (_failed) {
      return Align(
        alignment: Alignment.centerRight,
        child: TextButton.icon(
          onPressed: () => setState(() {
            _start();
            _startRoute();
          }),
          icon: const Icon(Icons.refresh, size: 18),
          label: const Text('지도 다시 시도'),
          style: TextButton.styleFrom(
            foregroundColor: const Color(0xFF914B33),
            minimumSize: const Size(0, 48),
          ),
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            height: mapHeight,
            width: double.infinity,
            child: ClipRRect(
              borderRadius: BorderRadius.zero,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  _session!.buildView(),
                  if (_ready && _routeLoading)
                    Positioned(
                      top: 14,
                      left: 14,
                      width: 34,
                      child: Semantics(
                        label: '경로 불러오는 중',
                        child: const LinearProgressIndicator(
                          minHeight: 2,
                          color: Color(0xFF914B33),
                          backgroundColor: Color(0xFFFFF8F3),
                        ),
                      ),
                    ),
                  if (_ready &&
                      !_routeLoading &&
                      _route != null &&
                      _route!.status != 'ready')
                    Positioned(
                      top: 8,
                      left: 8,
                      right: 100,
                      child: Align(
                        alignment: Alignment.topLeft,
                        child: Material(
                          color: const Color(0xFFFFFDFB),
                          borderRadius: BorderRadius.circular(10),
                          child: _route!.canRetry
                              ? TextButton.icon(
                                  onPressed: () => setState(_startRoute),
                                  icon: const Icon(Icons.refresh, size: 16),
                                  label: const Text('경로 다시 시도'),
                                  style: TextButton.styleFrom(
                                    foregroundColor: const Color(0xFF914B33),
                                    minimumSize: const Size(0, 40),
                                    textStyle: const TextStyle(fontSize: 12),
                                  ),
                                )
                              : const Padding(
                                  padding: EdgeInsets.symmetric(
                                    horizontal: 10,
                                    vertical: 8,
                                  ),
                                  child: Text(
                                    '경로를 표시할 수 없어요',
                                    style: TextStyle(
                                      fontSize: 12,
                                      color: Color(0xFF914B33),
                                    ),
                                  ),
                                ),
                        ),
                      ),
                    ),
                  if (!_ready)
                    ColoredBox(
                      color: Color(0xFFFFF8F3),
                      child: Center(
                        child: Semantics(
                          label: '지도 불러오는 중',
                          child: SizedBox(
                            width: 24,
                            height: 24,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Color(0xFF914B33),
                            ),
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _WebViewMapSession implements CourseMapSession {
  final ValueChanged<String> _onMessage;
  final VoidCallback _onFailure;
  final WebViewController _controller = WebViewController();
  bool _closed = false;
  String _origin = '';

  _WebViewMapSession(this._onMessage, this._onFailure);

  @override
  Future<void> load(String html, String origin) async {
    _origin = origin;
    await _controller.setJavaScriptMode(JavaScriptMode.unrestricted);
    await _controller.setBackgroundColor(const Color(0xFFFFF8F3));
    await _controller.addJavaScriptChannel(
      'CourseMapBridge',
      onMessageReceived: (message) {
        if (!_closed) _onMessage(message.message);
      },
    );
    await _controller.setNavigationDelegate(
      NavigationDelegate(
        onWebResourceError: (error) {
          if (!_closed && error.isForMainFrame == true) _onFailure();
        },
        onNavigationRequest: (request) async {
          if (_closed) return NavigationDecision.prevent;
          final uri = Uri.tryParse(request.url);
          if (request.url == 'about:blank' ||
              (uri != null &&
                  const {'https', 'http'}.contains(uri.scheme) &&
                  uri.origin == Uri.parse(_origin).origin)) {
            return NavigationDecision.navigate;
          }
          // Leave the SDK's own logo/copyright links usable in the external app.
          if (uri != null &&
              const {'https', 'http'}.contains(uri.scheme) &&
              const {
                'map.kakao.com',
                'apis.map.kakao.com',
              }.contains(uri.host)) {
            try {
              await launchUrl(
                uri.replace(scheme: 'https'),
                mode: LaunchMode.externalApplication,
              );
            } catch (_) {}
          }
          return NavigationDecision.prevent;
        },
      ),
    );
    if (_closed) return;
    await _controller.loadHtmlString(html, baseUrl: '$origin/');
  }

  @override
  Future<void> update(String script) async {
    if (!_closed) await _controller.runJavaScript(script);
  }

  @override
  Widget buildView() => WebViewWidget(
    controller: _controller,
    gestureRecognizers: {
      Factory<EagerGestureRecognizer>(EagerGestureRecognizer.new),
    },
  );

  @override
  Future<void> close() async {
    _closed = true;
    try {
      await _controller.runJavaScript(
        'window.courseMap && window.courseMap.close();window.stop();',
      );
      await _controller.removeJavaScriptChannel('CourseMapBridge');
    } catch (_) {}
  }
}
