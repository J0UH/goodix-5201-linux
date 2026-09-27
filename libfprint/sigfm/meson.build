sigfm_sources = ['sigfm.cpp']

# OpenCV 5 renamed the pkg-config module, accept both
opencv = dependency('opencv5', 'opencv4', required: true)
# doctest is only needed for the SIGFM unit tests
doctest = dependency('doctest', required: false)

libsigfm = static_library('sigfm',
        sigfm_sources,
        dependencies: [opencv],
)

if doctest.found()
    sigfm_tests = executable('sigfm-tests', ['./tests.cpp'], dependencies: [doctest, opencv], link_with: [libsigfm])
endif
