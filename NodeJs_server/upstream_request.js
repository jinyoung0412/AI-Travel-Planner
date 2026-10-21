// One lifetime for the entire upstream response, including its body. A socket
// idle timeout alone can be extended indefinitely by small response chunks.
function upstreamRequest(req, res, timeout) {
    const controller = new AbortController();
    let timedOut = false;
    let disconnected = false;
    const disconnect = () => {
        disconnected = true;
        controller.abort();
    };
    const responseClosed = () => {
        if (!res.writableFinished) disconnect();
    };
    req.on('aborted', disconnect);
    res.on('close', responseClosed);
    const timer = setTimeout(() => {
        timedOut = true;
        controller.abort();
    }, timeout);
    timer.unref?.();
    if (req.aborted || res.destroyed) disconnect();

    return {
        signal: controller.signal,
        get timedOut() { return timedOut; },
        canRespond: () => !disconnected && !res.destroyed && !res.writableEnded,
        checkDeadline() {
            if (timedOut) {
                const error = new Error('Upstream deadline exceeded');
                error.code = 'ETIMEDOUT';
                throw error;
            }
        },
        dispose() {
            clearTimeout(timer);
            req.removeListener('aborted', disconnect);
            res.removeListener('close', responseClosed);
        },
    };
}

module.exports = { upstreamRequest };
