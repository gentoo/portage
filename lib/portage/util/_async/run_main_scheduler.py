
import signal

def run_main_scheduler(scheduler):
	"""
	Start and run an AsyncScheduler (or compatible object), and handle
	SIGINT or SIGTERM by calling its terminate() method and waiting
	for it to clean up after itself. If SIGINT or SIGTERM is received,
	return signum, else return None. Any previous SIGINT or SIGTERM
	signal handlers are automatically saved and restored before
	returning.
	"""

	received_signal = []

	def sighandler(signum, frame):
		signal.signal(signal.SIGINT, signal.SIG_IGN)
		signal.signal(signal.SIGTERM, signal.SIG_IGN)
		received_signal.append(signum)
		scheduler.terminate()

	earlier_sigint_handler = signal.signal(signal.SIGINT, sighandler)
	earlier_sigterm_handler = signal.signal(signal.SIGTERM, sighandler)

	try:
		scheduler.start()
		scheduler.wait()
	finally:
		# Restore previous handlers
		if earlier_sigint_handler is not None:
			signal.signal(signal.SIGINT, earlier_sigint_handler)
		else:
			signal.signal(signal.SIGINT, signal.SIG_DFL)
		if earlier_sigterm_handler is not None:
			signal.signal(signal.SIGTERM, earlier_sigterm_handler)
		else:
			signal.signal(signal.SIGTERM, signal.SIG_DFL)

	if received_signal:
		return received_signal[0]
	return None
