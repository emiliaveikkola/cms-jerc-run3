##############################################
#  Automatic .d File Generation Makefile
##############################################

# Compiler and standard
GCC       = g++ -g -std=c++17

# ROOT flags
ROOT_L    = `root-config --libs`
ROOT_I    = -I`root-config --incdir` -I./header

# Directories
SRCDIR    = cpp
OBJDIR    = obj

# Source and object files
SOURCES   := $(wildcard $(SRCDIR)/*.cpp)
OBJECTS   := $(patsubst $(SRCDIR)/%.cpp, $(OBJDIR)/%.o, $(SOURCES))
BINS      := runMain

# Compiler flags:
#   -MMD -MP to generate .d files for all headers automatically.
CXXFLAGS  = $(ROOT_I) -MMD -MP
LDFLAGS   = $(ROOT_L) -lstdc++fs

# Primary target: build the main executable
$(BINS): $(OBJECTS) main.cpp
	@echo "--> Creating executable $@"
	@$(GCC) main.cpp $(OBJECTS) -o $@ $(CXXFLAGS) $(LDFLAGS)

# Rule for building object files + .d dependencies
$(OBJDIR)/%.o : $(SRCDIR)/%.cpp
	@echo "--> Creating object $@"
	@mkdir -p $(OBJDIR)
	@$(GCC) -c $< -o $@ $(CXXFLAGS) $(LDFLAGS)

# Include automatically-generated dependency files
# Each .o has a matching .d that lists which headers it depends on.
-include $(OBJECTS:.o=.d)

clean:
	rm -f $(OBJDIR)/*.o $(OBJDIR)/*.d $(BINS)

.PHONY: clean

